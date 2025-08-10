# app/routers/client_import.py
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from io import BytesIO
from typing import Dict, Any, List, Tuple
import pandas as pd

from db.connection import get_db
from db.models import ClientData

router = APIRouter(prefix="/client", tags=["Client"])

# Excel → DB column mapping
COL_MAP = {
    "Client Name": "ClientName",
    "Mobile": "Mobile",
    "Pan": "Pan",
    "Email": "Email",
    "City": "City",
    "Product": "Product",
    "Pack": "Pack",
    "Total Paid": "TotalPaid",
    "Start From": "StartFrom",
    "End On": "EndOn",
    "Duration": "Duration",
    "Status": "Status",
    "Payment Date": "PaymentDate",
}

REQUIRED_AT_LEAST_ONE = ["Mobile", "Email", "Pan"]  # skip row if all missing


def _clean_cell(v: Any) -> str | None:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None


def _prepare_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Normalize headers (strip, exact match)
    df.columns = [str(c).strip() for c in df.columns]

    # Keep only columns we know about, then rename to model fields
    present = [c for c in df.columns if c in COL_MAP]
    if not present:
        raise ValueError("No known columns found in uploaded file.")

    df = df[present].rename(columns=COL_MAP)

    # Clean all cells
    for col in df.columns:
        df[col] = df[col].map(_clean_cell)

    # Drop rows where all identifier fields are missing
    def has_minimum(row) -> bool:
        return any(_clean_cell(row.get(COL_MAP.get(k, k))) for k in REQUIRED_AT_LEAST_ONE)

    df = df[df.apply(has_minimum, axis=1)]

    # Convert to dicts
    return df.to_dict(orient="records")


def _find_existing(db: Session, mobile: str | None, pan: str | None, email: str | None) -> ClientData | None:
    """
    Simple dedupe strategy:
      1) Try (mobile & pan)
      2) Else try pan
      3) Else try mobile
      4) Else try email
    Adjust as per your business rules.
    """
    q = None
    if mobile and pan:
        q = db.query(ClientData).filter(ClientData.Mobile == mobile, ClientData.Pan == pan).first()
        if q:
            return q
    if pan:
        q = db.query(ClientData).filter(ClientData.Pan == pan).first()
        if q:
            return q
    if mobile:
        q = db.query(ClientData).filter(ClientData.Mobile == mobile).first()
        if q:
            return q
    if email:
        q = db.query(ClientData).filter(ClientData.Email == email).first()
        if q:
            return q
    return None


@router.post("/import-xlsx")
async def import_clients_from_xlsx(
    file: UploadFile = File(..., description="Excel .xlsx with headers like 'Client Name', 'Mobile', 'Pan', etc."),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload a .xlsx file")

    try:
        content = await file.read()
        df = pd.read_excel(BytesIO(content), dtype=str, engine="openpyxl")
        records = _prepare_records(df)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel: {e}")

    inserted = 0
    updated = 0
    skipped = 0
    errors: List[Tuple[int, str]] = []

    try:
        for idx, rec in enumerate(records, start=1):
            try:
                mobile = rec.get("Mobile")
                pan = rec.get("Pan")
                email = rec.get("Email")

                existing = _find_existing(db, mobile, pan, email)

                if existing:
                    # Update existing row fields that are present in the Excel
                    for k, v in rec.items():
                        if v is not None and hasattr(existing, k):
                            setattr(existing, k, v)
                    # Ensure not deleted
                    existing.isDelete = False if hasattr(existing, "isDelete") else existing.isDelete
                    updated += 1
                else:
                    # Create new row with defaults
                    row = ClientData(**rec, isDelete=False)
                    db.add(row)
                    inserted += 1
            except Exception as row_err:
                skipped += 1
                errors.append((idx, str(row_err)))

        db.commit()
    except Exception as txn_err:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {txn_err}")

    return {
        "status": "ok",
        "total_rows_in_file": len(records),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:25],  # cap in response
    }

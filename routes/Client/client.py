# app/routers/client_import.py
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Path
from sqlalchemy.orm import Session
from io import BytesIO
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, date
import re
import pandas as pd

from db.connection import get_db
from db.models import ClientData

router = APIRouter(prefix="/client", tags=["Client"])

# -------------------------
# Excel → DB column mapping
# -------------------------
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

# -------------------------
# Helpers
# -------------------------
DATE_FORMATS = [
    "%d-%b-%Y",     # 08-Apr-2024
    "%d-%b-%y",     # 02-Apr-24
    "%d %b %Y",     # 12 Apr 2024
    "%d-%m-%Y",     # 08-04-2024
    "%Y-%m-%d",     # 2024-04-08
    "%d/%m/%Y",     # 08/04/2024
    "%d %B %Y",     # 12 April 2024
]

def parse_date_or_none(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    # Try to normalize if like "12 Apr 2024 00:00:00"
    tokens = s.split()[0:3]
    if tokens:
        rough = " ".join(tokens)
        for fmt in ("%d %b %Y", "%d-%b-%Y"):
            try:
                return datetime.strptime(rough, fmt).date()
            except Exception:
                pass
    return None

_amt_cleaner = re.compile(r"[^\d.]")
def parse_amount_or_zero(s: Optional[str]) -> int:
    if s is None:
        return 0
    x = _amt_cleaner.sub("", str(s))
    if not x:
        return 0
    try:
        # treat as integer rupees (no paise in your sample)
        return int(float(x))
    except Exception:
        return 0

def _clean_cell(v: Any) -> Optional[str]:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None

def _prepare_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    df.columns = [str(c).strip() for c in df.columns]
    present = [c for c in df.columns if c in COL_MAP]
    if not present:
        raise ValueError("No known columns found in uploaded file.")
    df = df[present].rename(columns=COL_MAP)
    for col in df.columns:
        df[col] = df[col].map(_clean_cell)
    def has_minimum(row) -> bool:
        return any(_clean_cell(row.get(COL_MAP.get(k, k))) for k in REQUIRED_AT_LEAST_ONE)
    df = df[df.apply(has_minimum, axis=1)]
    return df.to_dict(orient="records")

def _find_existing(db: Session, mobile: Optional[str], pan: Optional[str], email: Optional[str]) -> Optional[ClientData]:
    q = None
    if mobile and pan:
        q = db.query(ClientData).filter(ClientData.Mobile == mobile, ClientData.Pan == pan).first()
        if q: return q
    if pan:
        q = db.query(ClientData).filter(ClientData.Pan == pan).first()
        if q: return q
    if mobile:
        q = db.query(ClientData).filter(ClientData.Mobile == mobile).first()
        if q: return q
    if email:
        q = db.query(ClientData).filter(ClientData.Email == email).first()
        if q: return q
    return None

def _row_to_dict(r: ClientData) -> Dict[str, Any]:
    return {
        "id": r.id,
        "ClientName": r.ClientName,
        "Mobile": r.Mobile,
        "Pan": r.Pan,
        "Email": r.Email,
        "City": r.City,
        "Product": r.Product,
        "Pack": r.Pack,
        "TotalPaid": r.TotalPaid,
        "StartFrom": r.StartFrom,
        "EndOn": r.EndOn,
        "Duration": r.Duration,
        "Status": r.Status,
        "PaymentDate": r.PaymentDate,
        "isDelete": r.isDelete,
    }

# -------------------------
# 1) Import XLSX (already done)
# -------------------------
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

    inserted = updated = skipped = 0
    errors: List[Tuple[int, str]] = []

    try:
        for idx, rec in enumerate(records, start=1):
            try:
                mobile = rec.get("Mobile")
                pan = rec.get("Pan")
                email = rec.get("Email")
                existing = _find_existing(db, mobile, pan, email)
                if existing:
                    for k, v in rec.items():
                        if v is not None and hasattr(existing, k):
                            setattr(existing, k, v)
                    existing.isDelete = False if hasattr(existing, "isDelete") else existing.isDelete
                    updated += 1
                else:
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
        "errors": errors[:25],
    }

# ------------------------------------------------------------
# 2) Get all clients with filters (date range, price, search)
# ------------------------------------------------------------
@router.get("/list")
def list_clients(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1),
    include_deleted: bool = Query(False),
    q: Optional[str] = Query(None, description="Global search across name/mobile/pan/email/city/product/status"),
    product: Optional[str] = None,
    pack: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[str] = None,
    date_field: str = Query("PaymentDate", regex="^(PaymentDate|StartFrom|EndOn)$"),
    date_from: Optional[date] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[date] = Query(None, description="YYYY-MM-DD"),
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
):
    qset = db.query(ClientData)
    if not include_deleted:
        qset = qset.filter(ClientData.isDelete == False)

    # cheap DB-side equals filters
    if product: qset = qset.filter(ClientData.Product.ilike(f"%{product}%"))
    if pack:    qset = qset.filter(ClientData.Pack.ilike(f"%{pack}%"))
    if city:    qset = qset.filter(ClientData.City.ilike(f"%{city}%"))
    if status:  qset = qset.filter(ClientData.Status.ilike(f"%{status}%"))
    if q:
        patt = f"%{q}%"
        qset = qset.filter(
            (ClientData.ClientName.ilike(patt)) |
            (ClientData.Mobile.ilike(patt)) |
            (ClientData.Pan.ilike(patt)) |
            (ClientData.Email.ilike(patt)) |
            (ClientData.City.ilike(patt)) |
            (ClientData.Product.ilike(patt)) |
            (ClientData.Status.ilike(patt))
        )

    # Pull and do date/amount filtering in Python due to string columns
    rows: List[ClientData] = qset.all()

    def pass_filters(r: ClientData) -> bool:
        # amount
        amt = parse_amount_or_zero(r.TotalPaid)
        if min_price is not None and amt < min_price:
            return False
        if max_price is not None and amt > max_price:
            return False
        # dates
        src = getattr(r, date_field)
        d = parse_date_or_none(src)
        if date_from and (d is None or d < date_from):
            return False
        if date_to and (d is None or d > date_to):
            return False
        return True

    filtered = [r for r in rows if pass_filters(r)]
    total = len(filtered)
    start = (page - 1) * limit
    end = start + limit
    page_items = filtered[start:end]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "items": [_row_to_dict(r) for r in page_items],
        "sumTotalPaidOnPage": sum(parse_amount_or_zero(r.TotalPaid) for r in page_items),
        "sumTotalPaidAll": sum(parse_amount_or_zero(r.TotalPaid) for r in filtered),
    }

# ------------------------------------------------------------
# 3) Product summaries (overall, monthly, yearly)
# ------------------------------------------------------------
@router.get("/products/summary")
def product_summary(
    db: Session = Depends(get_db),
    include_deleted: bool = Query(False),
    date_field: str = Query("PaymentDate", regex="^(PaymentDate|StartFrom|EndOn)$"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    qset = db.query(ClientData)
    if not include_deleted:
        qset = qset.filter(ClientData.isDelete == False)
    rows = qset.all()

    # Aggregations
    total_by_product: Dict[str, int] = {}
    monthly: Dict[str, int] = {}  # "YYYY-MM" -> sum
    yearly: Dict[int, int] = {}

    for r in rows:
        d = parse_date_or_none(getattr(r, date_field))
        if date_from and (d is None or d < date_from):
            continue
        if date_to and (d is None or d > date_to):
            continue
        product = (r.Product or "").strip() or "Unknown"
        amt = parse_amount_or_zero(r.TotalPaid)

        total_by_product[product] = total_by_product.get(product, 0) + amt

        if d:
            ym = f"{d.year:04d}-{d.month:02d}"
            monthly[ym] = monthly.get(ym, 0) + amt
            yearly[d.year] = yearly.get(d.year, 0) + amt

    return {
        "by_product": [{"product": k, "total": v} for k, v in sorted(total_by_product.items(), key=lambda x: x[0])],
        "monthly": [{"month": k, "total": v} for k, v in sorted(monthly.items(), key=lambda x: x[0])],
        "yearly": [{"year": k, "total": v} for k, v in sorted(yearly.items(), key=lambda x: x[0])],
        "overall_total": sum(total_by_product.values()),
    }

# Distinct product list (helper)
@router.get("/products")
def list_products(db: Session = Depends(get_db), include_deleted: bool = Query(False)):
    qset = db.query(ClientData.Product)
    if not include_deleted:
        qset = qset.filter(ClientData.isDelete == False)
    products = sorted({(p or "").strip() for (p,) in qset.distinct().all() if (p or "").strip()})
    return {"products": products}

# ------------------------------------------------------------
# 4) Unique client total payment (grouped by Mobile)
# ------------------------------------------------------------
@router.get("/unique-clients/total")
def unique_clients_total(
    db: Session = Depends(get_db),
    include_deleted: bool = Query(False),
    date_field: str = Query("PaymentDate", regex="^(PaymentDate|StartFrom|EndOn)$"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    qset = db.query(ClientData)
    if not include_deleted:
        qset = qset.filter(ClientData.isDelete == False)
    rows = qset.all()

    by_client: Dict[str, int] = {}
    for r in rows:
        d = parse_date_or_none(getattr(r, date_field))
        if date_from and (d is None or d < date_from):
            continue
        if date_to and (d is None or d > date_to):
            continue
        key = (r.Mobile or r.Email or r.Pan or f"id-{r.id}")  # fallback
        by_client[key] = by_client.get(key, 0) + parse_amount_or_zero(r.TotalPaid)

    items = [{"client_key": k, "total": v} for k, v in sorted(by_client.items(), key=lambda x: (-x[1], x[0]))]
    return {
        "unique_clients": len(by_client),
        "overall_total": sum(by_client.values()),
        "items": items,
    }

# ------------------------------------------------------------
# 5) Unique client + product total (Mobile, Product)
# ------------------------------------------------------------
@router.get("/unique-client-product/total")
def unique_client_product_total(
    db: Session = Depends(get_db),
    include_deleted: bool = Query(False),
    date_field: str = Query("PaymentDate", regex="^(PaymentDate|StartFrom|EndOn)$"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    qset = db.query(ClientData)
    if not include_deleted:
        qset = qset.filter(ClientData.isDelete == False)
    rows = qset.all()

    by_pair: Dict[Tuple[str, str], int] = {}
    for r in rows:
        d = parse_date_or_none(getattr(r, date_field))
        if date_from and (d is None or d < date_from):
            continue
        if date_to and (d is None or d > date_to):
            continue
        client_key = (r.Mobile or r.Email or r.Pan or f"id-{r.id}")
        product = (r.Product or "").strip() or "Unknown"
        key = (client_key, product)
        by_pair[key] = by_pair.get(key, 0) + parse_amount_or_zero(r.TotalPaid)

    items = [
        {"client_key": ck, "product": pd, "total": amt}
        for (ck, pd), amt in sorted(by_pair.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))
    ]
    return {
        "unique_pairs": len(by_pair),
        "overall_total": sum(by_pair.values()),
        "items": items,
    }

# ------------------------------------------------------------
# 1 & 6) Delete client
#   a) by id (single record)
#   b) by mobile (all records for that client) -> soft delete all
# ------------------------------------------------------------
@router.delete("/delete/{id}")
def delete_by_id(id: int = Path(..., ge=1), db: Session = Depends(get_db)):
    row = db.query(ClientData).filter(ClientData.id == id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Client record not found")
    row.isDelete = True
    db.commit()
    return {"status": "ok", "message": f"Record {id} marked deleted"}

@router.post("/delete-by-mobile")
def delete_by_mobile(
    mobile: str = Query(..., min_length=5),
    db: Session = Depends(get_db),
):
    rows = db.query(ClientData).filter(ClientData.Mobile == mobile).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No records found for this mobile")
    for r in rows:
        r.isDelete = True
    db.commit()
    return {"status": "ok", "message": f"{len(rows)} records for {mobile} marked deleted"}

# ------------------------------------------------------------
# 7) Get deleted clients
# ------------------------------------------------------------
@router.get("/deleted")
def list_deleted_clients(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1),
):
    qset = db.query(ClientData).filter(ClientData.isDelete == True)
    total = qset.count()
    items = qset.offset((page - 1) * limit).limit(limit).all()
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "items": [_row_to_dict(r) for r in items],
    }

# ------------------------------------------------------------
# 8) Recover client
#   a) by id
#   b) by mobile (all rows for that client)
# ------------------------------------------------------------
@router.post("/recover/{id}")
def recover_by_id(id: int = Path(..., ge=1), db: Session = Depends(get_db)):
    row = db.query(ClientData).filter(ClientData.id == id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Client record not found")
    row.isDelete = False
    db.commit()
    return {"status": "ok", "message": f"Record {id} recovered"}

@router.post("/recover-by-mobile")
def recover_by_mobile(
    mobile: str = Query(..., min_length=5),
    db: Session = Depends(get_db),
):
    rows = db.query(ClientData).filter(ClientData.Mobile == mobile).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No records found for this mobile")
    for r in rows:
        r.isDelete = False
    db.commit()
    return {"status": "ok", "message": f"{len(rows)} records for {mobile} recovered"}

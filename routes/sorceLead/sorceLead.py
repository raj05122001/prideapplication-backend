# routes/source_scrap_lead.py
from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from sqlalchemy import or_, asc, desc
from sqlalchemy.orm import Session

# ---- your project deps ----
from db.connection import get_db
from db.models import sourceScrapLead


# =============================================================================
# P Y D A N T I C   S C H E M A S
# =============================================================================
class SourceScrapLeadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: Optional[str] = None
    director_name: Optional[str] = None
    father_name: Optional[str] = None
    gender: Optional[str] = None                         # "male"/"female"/...
    marital_status: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    alternate_mobile: Optional[str] = None
    aadhaar: Optional[str] = None
    pan: Optional[str] = None
    gstin: Optional[str] = "URP"

    state: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = None

    dob: Optional[date] = None
    occupation: Optional[str] = None
    experience: Optional[str] = None
    investment: Optional[str] = None
    source: Optional[str] = None

    @field_validator("gender")
    @classmethod
    def _normalize_gender(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if isinstance(v, str) else v


class SourceScrapLeadCreate(SourceScrapLeadBase):
    """All fields optional; add required ones here if you need."""


class SourceScrapLeadUpdate(SourceScrapLeadBase):
    """Partial update; same fields as base."""


class SourceScrapLeadOut(SourceScrapLeadBase):
    id: int


# =============================================================================
# S E R V I C E   H E L P E R S
# =============================================================================
def create_scrap_lead(db: Session, payload: SourceScrapLeadCreate) -> sourceScrapLead:
    obj = sourceScrapLead(**payload.model_dump(exclude_unset=True))
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_scrap_lead(db: Session, lead_id: int) -> Optional[sourceScrapLead]:
    return db.query(sourceScrapLead).filter(sourceScrapLead.id == lead_id).first()


def update_scrap_lead(
    db: Session, lead_id: int, payload: SourceScrapLeadUpdate
) -> Optional[sourceScrapLead]:
    obj = get_scrap_lead(db, lead_id)
    if not obj:
        return None
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def delete_scrap_lead(db: Session, lead_id: int) -> bool:
    obj = get_scrap_lead(db, lead_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


def list_scrap_leads(
    db: Session,
    q: Optional[str],
    email: Optional[str],
    mobile: Optional[str],
    state: Optional[str],
    city: Optional[str],
    source: Optional[str],
    page: int,
    limit: int,
    sort_by: str,
    order: str,
) -> Tuple[List[sourceScrapLead], int]:
    query = db.query(sourceScrapLead)

    # free-text search (on common columns)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                sourceScrapLead.full_name.ilike(like),
                sourceScrapLead.email.ilike(like),
                sourceScrapLead.mobile.ilike(like),
                sourceScrapLead.state.ilike(like),
                sourceScrapLead.city.ilike(like),
                sourceScrapLead.source.ilike(like),
            )
        )

    # precise filters (case-insensitive)
    if email:
        query = query.filter(sourceScrapLead.email.ilike(email))
    if mobile:
        query = query.filter(sourceScrapLead.mobile.ilike(mobile))
    if state:
        query = query.filter(sourceScrapLead.state.ilike(state))
    if city:
        query = query.filter(sourceScrapLead.city.ilike(city))
    if source:
        query = query.filter(sourceScrapLead.source.ilike(source))

    total = query.count()

    # sorting
    sort_map = {
        "id": sourceScrapLead.id,
        "full_name": sourceScrapLead.full_name,
        "email": sourceScrapLead.email,
        "mobile": sourceScrapLead.mobile,
        "state": sourceScrapLead.state,
        "city": sourceScrapLead.city,
        "source": sourceScrapLead.source,
        "dob": sourceScrapLead.dob,
    }
    sort_col = sort_map.get((sort_by or "id").lower(), sourceScrapLead.id)
    direction = (order or "desc").lower()
    query = query.order_by(asc(sort_col) if direction == "asc" else desc(sort_col))

    rows = query.offset((page - 1) * limit).limit(limit).all()
    return rows, total


# =============================================================================
# R O U T E R
# =============================================================================
router = APIRouter(prefix="/scrap-leads", tags=["Source Scrap Lead"])

@router.post("", response_model=SourceScrapLeadOut, status_code=201)
def create_lead(payload: SourceScrapLeadCreate, db: Session = Depends(get_db)):
    return create_scrap_lead(db, payload)


@router.get("/{lead_id}", response_model=SourceScrapLeadOut)
def fetch_one(lead_id: int, db: Session = Depends(get_db)):
    obj = get_scrap_lead(db, lead_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Lead not found")
    return obj


@router.patch("/{lead_id}", response_model=SourceScrapLeadOut)
@router.put("/{lead_id}", response_model=SourceScrapLeadOut)
def update_one(lead_id: int, payload: SourceScrapLeadUpdate, db: Session = Depends(get_db)):
    obj = update_scrap_lead(db, lead_id, payload)
    if not obj:
        raise HTTPException(status_code=404, detail="Lead not found")
    return obj


@router.delete("/{lead_id}", status_code=204)
def delete_one(lead_id: int, db: Session = Depends(get_db)):
    ok = delete_scrap_lead(db, lead_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
    return  # 204 No Content


@router.get("", response_model=Dict[str, Any])
def list_many(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="Free text search"),
    email: Optional[str] = None,
    mobile: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    sort_by: str = Query("id", description="id|full_name|email|mobile|state|city|source|dob"),
    order: str = Query("desc", description="asc|desc"),
):
    rows, total = list_scrap_leads(
        db,
        q=q, email=email, mobile=mobile, state=state, city=city, source=source,
        page=page, limit=limit, sort_by=sort_by, order=order,
    )
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [SourceScrapLeadOut.model_validate(r) for r in rows],
    }

from fastapi import APIRouter, Depends, HTTPException
from datetime import date
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import UserDetails

router = APIRouter(prefix="/plan", tags=["plan"])

@router.get(
    "/check-plan/{phone_number}",
    summary="Check user's service-plan status by phone number"
)
def check_plan(phone_number: str, db: Session = Depends(get_db)):
    # 1. Fetch user
    user = db.query(UserDetails).filter_by(phone_number=phone_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 2. Parse stored date (assuming 'YYYY-MM-DD')
    try:
        active_date = date.fromisoformat(user.service_active_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=500, detail="Invalid service_active_date format")
    
    today = date.today()

    # 3. Compare and return
    if active_date >= today:
        return {
            "message": "✅ Your plan is active. Enjoy our services!",
            "login": True,
            "service": user.service
        }
    else:
        return {
            "message": "⚠️ Your plan has expired. Please recharge to renew your access.",
            "login": False,
            "service": user.service
        }

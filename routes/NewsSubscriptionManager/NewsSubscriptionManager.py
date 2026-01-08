from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import PushToken, UserDetails
from datetime import datetime, timezone
import logging, traceback
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from db.connection import get_db
from db.models import PushToken

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/notification",
    tags=["notification"],
)

# Request Models
class TokenRegister(BaseModel):
    user_id: str = Field(..., min_length=1)
    push_token: str = Field(..., min_length=10)

# Response Models
class TokenResponse(BaseModel):
    id: int
    user_id: str
    token: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            # Handle datetime serialization
            'datetime': lambda v: v.isoformat() if v else None
        }

class TokensListResponse(BaseModel):
    tokens: List[TokenResponse]
    total_count: int


def _now_utc():
    return datetime.now(timezone.utc)

@router.post("/users/register-push-token", response_model=TokenResponse)
def register_token(payload: TokenRegister, db: Session = Depends(get_db)):
    try:
        now = _now_utc()

        # 1) If THIS token already exists for some other user, re-assign it
        token_row = (
            db.query(PushToken)
            .filter(PushToken.token == payload.push_token)
            .first()
        )
        if token_row and token_row.user_id != payload.user_id:
            token_row.user_id = payload.user_id
            if hasattr(token_row, "updated_at"):
                token_row.updated_at = now
            db.flush()
            db.commit()
            db.refresh(token_row)

            return TokenResponse(
                id=token_row.id,
                user_id=token_row.user_id,
                token=token_row.token,
                updated_at=token_row.updated_at.isoformat() if getattr(token_row, "updated_at", None) else None,
            )

        # 2) Else: upsert by user_id
        user_row = (
            db.query(PushToken)
            .filter(PushToken.user_id == payload.user_id)
            .first()
        )

        if user_row:
            user_row.token = payload.push_token
            if hasattr(user_row, "updated_at"):
                user_row.updated_at = now
        else:
            kwargs = dict(user_id=payload.user_id, token=payload.push_token)
            if hasattr(PushToken, "updated_at"):
                kwargs["updated_at"] = now
            user_row = PushToken(**kwargs)
            db.add(user_row)

        db.flush()
        db.commit()
        db.refresh(user_row)

        return TokenResponse(
            id=user_row.id,
            user_id=user_row.user_id,
            token=user_row.token,
            updated_at=user_row.updated_at.isoformat() if getattr(user_row, "updated_at", None) else None,
        )

    except IntegrityError as e:
        db.rollback()
        logger.error("IntegrityError register-push-token: %s", str(e))
        logger.error(traceback.format_exc())
        # return 409 instead of 500 (conflict)
        raise HTTPException(status_code=409, detail="Token already mapped to another user (unique constraint).")

    except Exception as e:
        db.rollback()
        logger.error("register-push-token failed: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to register token: {str(e)}")

@router.get("/users/push-tokens")
def get_all_tokens(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Get all push tokens with pagination"""
    try:
        tokens = db.query(PushToken).offset(skip).limit(limit).all()
        total_count = db.query(PushToken).count()
        
        # Manually convert to dict to avoid serialization issues
        tokens_data = []
        for token in tokens:
            tokens_data.append({
                "id": token.id,
                "user_id": token.user_id,
                "token": token.token,
                "updated_at": str(token.updated_at) if token.updated_at else None
            })
        
        return {
            "tokens": tokens_data,
            "total_count": total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch tokens")

@router.get("/users/{user_id}/push-token")
def get_token_by_user_id(
    user_id: str,
    db: Session = Depends(get_db),
):
    """Get push token for a specific user"""
    try:
        db_token = (
            db.query(PushToken)
            .filter(PushToken.user_id == user_id)
            .first()
        )
        
        if not db_token:
            raise HTTPException(
                status_code=404, 
                detail=f"Push token not found for user_id: {user_id}"
            )
        
        # Manually convert to dict
        return {
            "id": db_token.id,
            "user_id": db_token.user_id,
            "token": db_token.token,
            "updated_at": str(db_token.updated_at) if db_token.updated_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch token")

@router.delete("/users/{user_id}/push-token")
def delete_token_by_user_id(
    user_id: str,
    db: Session = Depends(get_db),
):
    """Delete push token for a specific user"""
    try:
        db_token = (
            db.query(PushToken)
            .filter(PushToken.user_id == user_id)
            .first()
        )
        
        if not db_token:
            raise HTTPException(
                status_code=404, 
                detail=f"Push token not found for user_id: {user_id}"
            )
        
        db.delete(db_token)
        db.commit()
        return {"status": "ok", "message": "Token deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete token")
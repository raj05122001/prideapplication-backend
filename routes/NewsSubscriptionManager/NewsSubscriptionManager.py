from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import PushToken, UserDetails

router = APIRouter(
    prefix="/notification",
    tags=["notification"],
)

# Request Models
class TokenRegister(BaseModel):
    user_id: str
    push_token: str

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

@router.post("/users/register-push-token")
def register_token(
    payload: TokenRegister,
    db: Session = Depends(get_db),
):
    """Register or update a push token for a user"""
    try:
        db_token = (
            db.query(PushToken)
            .filter(PushToken.user_id == payload.user_id)
            .first()
        )
        if db_token:
            db_token.token = payload.push_token
            db.refresh(db_token)
        else:
            db_token = PushToken(
                user_id=payload.user_id,
                token=payload.push_token
            )
            db.add(db_token)
        db.commit()
        return {"status": "ok", "message": "Token registered successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to register token")

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
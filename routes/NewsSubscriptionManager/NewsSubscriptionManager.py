from datetime import datetime, timezone
import logging
import traceback
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import PushToken

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/notification",
    tags=["notification"],
)

# -----------------------------
# Request Models
# -----------------------------
class TokenRegister(BaseModel):
    user_id: str = Field(..., min_length=1)
    push_token: str = Field(..., min_length=10)  # FCM tokens are usually long


# -----------------------------
# Response Models
# -----------------------------
class TokenResponse(BaseModel):
    id: int
    user_id: str
    token: str
    updated_at: Optional[str] = None  # iso string

    class Config:
        from_attributes = True


class TokensListResponse(BaseModel):
    tokens: List[TokenResponse]
    total_count: int


def _now_utc():
    return datetime.now(timezone.utc)


# -----------------------------
# Routes
# -----------------------------
@router.post("/users/register-push-token", response_model=TokenResponse)
def register_token(
    payload: TokenRegister,
    db: Session = Depends(get_db),
):
    """
    Register or update a push token for a user.
    NOTE: This should never block login flow on client side.
    """
    try:
        # find existing
        db_token = (
            db.query(PushToken)
            .filter(PushToken.user_id == payload.user_id)
            .first()
        )

        now = _now_utc()

        if db_token:
            db_token.token = payload.push_token
            # If your DB column is NOT NULL or you want to track updates:
            if hasattr(db_token, "updated_at"):
                db_token.updated_at = now
        else:
            # If your model has updated_at/created_at, set them too
            kwargs = dict(user_id=payload.user_id, token=payload.push_token)
            if hasattr(PushToken, "updated_at"):
                kwargs["updated_at"] = now
            db_token = PushToken(**kwargs)
            db.add(db_token)

        db.flush()      # ensures id is generated before response
        db.commit()
        db.refresh(db_token)

        # Convert updated_at to iso string for TokenResponse(updated_at: str)
        return TokenResponse(
            id=db_token.id,
            user_id=db_token.user_id,
            token=db_token.token,
            updated_at=db_token.updated_at.isoformat() if getattr(db_token, "updated_at", None) else None,
        )

    except Exception as e:
        db.rollback()
        logger.error("register-push-token failed: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to register token: {str(e)}")


@router.get("/users/push-tokens", response_model=TokensListResponse)
def get_all_tokens(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    try:
        tokens = db.query(PushToken).offset(skip).limit(limit).all()
        total_count = db.query(PushToken).count()

        tokens_out: List[TokenResponse] = []
        for t in tokens:
            tokens_out.append(
                TokenResponse(
                    id=t.id,
                    user_id=t.user_id,
                    token=t.token,
                    updated_at=t.updated_at.isoformat() if getattr(t, "updated_at", None) else None,
                )
            )

        return TokensListResponse(tokens=tokens_out, total_count=total_count)

    except Exception as e:
        logger.error("get_all_tokens failed: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch tokens: {str(e)}")


@router.get("/users/{user_id}/push-token", response_model=TokenResponse)
def get_token_by_user_id(
    user_id: str,
    db: Session = Depends(get_db),
):
    try:
        db_token = (
            db.query(PushToken)
            .filter(PushToken.user_id == user_id)
            .first()
        )

        if not db_token:
            raise HTTPException(
                status_code=404,
                detail=f"Push token not found for user_id: {user_id}",
            )

        return TokenResponse(
            id=db_token.id,
            user_id=db_token.user_id,
            token=db_token.token,
            updated_at=db_token.updated_at.isoformat() if getattr(db_token, "updated_at", None) else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_token_by_user_id failed: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch token: {str(e)}")


@router.delete("/users/{user_id}/push-token")
def delete_token_by_user_id(
    user_id: str,
    db: Session = Depends(get_db),
):
    try:
        db_token = (
            db.query(PushToken)
            .filter(PushToken.user_id == user_id)
            .first()
        )

        if not db_token:
            raise HTTPException(
                status_code=404,
                detail=f"Push token not found for user_id: {user_id}",
            )

        db.delete(db_token)
        db.commit()
        return {"status": "ok", "message": "Token deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("delete_token_by_user_id failed: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to delete token: {str(e)}")

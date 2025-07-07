# main.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import httpx
from sqlalchemy import Column, Integer, DateTime, func   

from config import (
    CASHFREE_APP_ID,
    CASHFREE_SECRET_KEY,
    CASHFREE_PRODUCTION,
)

router = APIRouter(
    prefix="/payment",
    tags=["payment"],
)

### ─── Models ────────────────────────────────────────────────────────────────

class CustomerDetails(BaseModel):
    customer_id:    Column(Integer, primary_key=True, index=True)
    customer_email: str
    customer_phone: str

class CreateOrderRequest(BaseModel):
    order_amount:   float
    order_currency: str = Field("INR", min_length=3, max_length=3)
    customer_details: CustomerDetails
    order_note:     str | None = None
    payment_type:     str | None = None
    payment_status:     str | None = None
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

### ─── Helpers ───────────────────────────────────────────────────────────────

def _base_url() -> str:
    return (
        "https://api.cashfree.com/pg"
        if CASHFREE_PRODUCTION
        else "https://sandbox.cashfree.com/pg"
    )

def _headers() -> dict[str, str]:
    return {
        "Content-Type":    "application/json",
        "x-client-id":     CASHFREE_APP_ID,
        "x-client-secret": CASHFREE_SECRET_KEY,
        "x-api-version":   "2022-01-01",
    }

async def _call_cashfree(method: str, path: str, json: dict | None = None):
    url = _base_url() + path
    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=_headers(), json=json)
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


### ─── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/api/create-order")
async def create_order(req: CreateOrderRequest):
    """
    Create a new Cashfree order.
    Returns JSON with `order_id` and `payment_link`.
    """
    return await _call_cashfree("POST", "/orders", json=req.dict())


@router.get("/orders/{order_id}/status")
async def get_order_status(order_id: str):
    """
    Fetch order status from Cashfree.
    """
    return await _call_cashfree("GET", f"/orders/{order_id}")

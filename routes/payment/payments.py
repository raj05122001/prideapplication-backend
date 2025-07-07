# routes/payment/payments.py

from fastapi import APIRouter, HTTPException
from httpx import AsyncClient
from db.schema import CreateOrderRequest
from config import CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_PRODUCTION

router = APIRouter(prefix="/payment", tags=["payment"])

def _base_url() -> str:
    return "https://api.cashfree.com/pg" if CASHFREE_PRODUCTION else "https://sandbox.cashfree.com/pg"

def _headers() -> dict[str,str]:
    return {
        "Content-Type":  "application/json",
        "x-client-id":   CASHFREE_APP_ID,
        "x-client-secret": CASHFREE_SECRET_KEY,
        "x-api-version": "2022-01-01",
    }

async def _call_cashfree(method: str, path: str, json: dict | None = None):
    url = _base_url() + path
    async with AsyncClient() as client:
        resp = await client.request(method, url, headers=_headers(), json=json)
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@router.post("/api/create-order")
async def create_order(req: CreateOrderRequest):
    return await _call_cashfree("POST", "/orders", json=req.model_dump())

@router.get("/orders/{order_id}/status")
async def get_order_status(order_id: str):
    return await _call_cashfree("GET", f"/orders/{order_id}")

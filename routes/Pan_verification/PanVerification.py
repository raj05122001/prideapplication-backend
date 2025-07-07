from fastapi import APIRouter, HTTPException, Form, Depends
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.connection import get_db
from db.models import PanVerification
from config import PAN_API_ID, PAN_API_KEY, PAN_TASK_ID_1, PAN_TASK_ID_2
import asyncio

router = APIRouter(tags=["Pan Verification"])


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.models import PanVerification

async def post_with_retries(
    url: str,
    headers: dict,
    payload: dict,
    *,
    max_retries: int | None = None,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
) -> dict:
    """
    POST to `url` with httpx until success.

    Args:
      url: request URL
      headers: headers dict
      payload: JSON body
      max_retries: maximum number of attempts (None = infinite)
      initial_delay: seconds to wait before first retry
      backoff_factor: multiplier for delay on each failure
      max_delay: cap for delay

    Returns:
      Parsed JSON response on HTTP 2xx

    Raises:
      HTTPException once max_retries is exceeded.
    """
    attempt = 0
    delay = initial_delay

    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

        except httpx.HTTPStatusError as exc:
            # server returned 4xx/5xx
            status = exc.response.status_code
            detail = f"Error calling {url}: {exc.response.text}"
        except httpx.HTTPError as exc:
            # network error, timeouts, etc.
            status = 500
            detail = f"Error calling {url}: {str(exc)}"
        # if we reach here, it failed
        attempt += 1
        if max_retries is not None and attempt > max_retries:
            raise HTTPException(status_code=status, detail=detail)

        # wait, then retry
        await asyncio.sleep(delay)
        delay = min(delay * backoff_factor, max_delay)


async def update_api_count(db, pannumber: str):
    # Run the execute call in a thread to avoid blocking
    result = await asyncio.to_thread(db.execute, select(PanVerification).where(PanVerification.PANnumber == pannumber))
    pan_entry = result.scalar_one_or_none()  # Process result synchronously

    # if pan_entry and pan_entry.APICount >= 2:
    #     raise HTTPException(status_code=429, detail="API limit exceeded. Maximum 2 requests allowed per PAN number.")

    if pan_entry:
        pan_entry.APICount += 1
    else:
        pan_entry = PanVerification(PANnumber=pannumber, APICount=1)
        db.add(pan_entry)

    # Commit and refresh in thread as well
    await asyncio.to_thread(db.commit)
    await asyncio.to_thread(db.refresh, pan_entry)

@router.post("/pro-pan-verification")
async def verification(
    pannumber: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # await update_api_count(db, pannumber)

    url = "https://live.zoop.one/api/v1/in/identity/pan/pro"
    headers = {
        "app-id": PAN_API_ID,
        "api-key": PAN_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "mode": "sync",
        "data": {
            "customer_pan_number": pannumber,
            "consent": "Y",
            "consent_text": "I hear by declare my consent agreement for fetching my information via ZOOP API"
        },
        "task_id": PAN_TASK_ID_1
    }

    data = await post_with_retries(
        url, headers, payload,
        max_retries=15,         # try up to 5 times
        initial_delay=2.0,     # wait 2s before first retry
        backoff_factor=1.5,    # increase delay by 1.5× each time
        max_delay=10.0,        # cap waiting at 10s
    )
    return data

@router.post("/pan-verification")
async def verification(
    pannumber: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await update_api_count(db, pannumber)

    url = "https://live.zoop.one/api/v1/in/identity/pan/lite"
    headers = {
        "app-id": PAN_API_ID,
        "api-key": PAN_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "mode": "sync",
        "data": {
            "customer_pan_number": pannumber,
            "consent": "Y",
            "consent_text": "I hereby declare my consent agreement for fetching my information via ZOOP API"
        },
        "task_id": PAN_TASK_ID_2
    }

    data = await post_with_retries(
        url, headers, payload,
        max_retries=15,         # try up to 5 times
        initial_delay=2.0,     # wait 2s before first retry
        backoff_factor=1.5,    # increase delay by 1.5× each time
        max_delay=10.0,        # cap waiting at 10s
    )
    return data

@router.post("/micro-pan-verification")
async def verification(
    pannumber: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # await update_api_count(db, pannumber)

    url = "https://live.zoop.one/api/v1/in/identity/pan/micro"
    headers = {
        "app-id": PAN_API_ID,
        "api-key": PAN_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "mode": "sync",
        "data": {
            "customer_pan_number": pannumber,
            "pan_details": True,
            "consent": "Y",
            "consent_text": "I hear by declare my consent agreement for fetching my information via ZOOP API"
        },
        "task_id": "f26eb21e-4c35-4491-b2d5-41fa0e545a34"
    }

    data = await post_with_retries(
        url, headers, payload,
        max_retries=15,         # try up to 5 times
        initial_delay=2.0,     # wait 2s before first retry
        backoff_factor=1.5,    # increase delay by 1.5× each time
        max_delay=10.0,        # cap waiting at 10s
    )
    return data
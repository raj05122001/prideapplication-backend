from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import APIRouter, Request, HTTPException, Depends, Response
import aioboto3
import json
from sqlalchemy.orm import Session
from db.connection import get_db
from routes.E_Stamp.DS_estamp import init_estamp
from routes.E_Stamp.Final_mail import Final_send_agreement
from db.models import EStamp
import httpx
from db.models import KYCUser
from routes.mail_service.kyc_agreement_mail import send_agreement
import base64
from config import CF_R2_ACCESS_KEY_ID,CF_R2_ACCOUNT_ID,CF_R2_REGION,CF_R2_SECRET_ACCESS_KEY
from urllib.parse import urlencode
from starlette.datastructures import QueryParams

def _append_query(url: str, qp: QueryParams) -> str:
    """Append incoming query params to target url (preserves existing ones)."""
    if not qp:
        return url
    sep = "&" if ("?" in url) else "?"
    return f"{url}{sep}{qp}"

def _safe_get(d: dict, *path, default=None):
    """Safely walk keys in nested dicts."""
    cur = d or {}
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur



router = APIRouter(tags=["Agreement KYC Redirect"])
S3_BUCKET_NAME = "pride-user-data"

# Middleware-like functionality for each endpoint
def set_cors_allow_all(response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"

async def write_json_to_s3(content: dict, key: str):
    """
    Asynchronously upload a dict as JSON to S3.
    
    :param content: The dict content to upload.
    :param key: The S3 object key (file path in S3).
    """
    session = aioboto3.Session()
    
    async with session.client(
        "s3",
        aws_access_key_id=CF_R2_ACCESS_KEY_ID,
        aws_secret_access_key=CF_R2_SECRET_ACCESS_KEY,
        region_name=CF_R2_REGION,
        endpoint_url=f"https://{CF_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    ) as s3_client:
        await s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(content).encode("utf-8"),  # ✅ Convert dict to JSON bytes
            ContentType="application/json"
        )
    
    print(f"✅ Uploaded {key} to s3://{S3_BUCKET_NAME}/{key}")

async def write_pdf_to_s3(pdf_bytes: bytes, key: str):
    """
    Asynchronously upload a PDF file to S3.
    
    :param pdf_bytes: The binary content of the PDF file.
    :param key: The S3 object key (file path in S3).
    """
    session = aioboto3.Session()
    
    async with session.client(
        "s3",
        aws_access_key_id=CF_R2_ACCESS_KEY_ID,
        aws_secret_access_key=CF_R2_SECRET_ACCESS_KEY,
        region_name=CF_R2_REGION,
        endpoint_url=f"https://{CF_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    ) as s3_client:
        await s3_client.put_object(
            Bucket=S3_BUCKET_NAME,  # Use the actual bucket name
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf"  # Correct MIME type for PDF
        )
    
    print(f"✅ Uploaded {key} to s3://{S3_BUCKET_NAME}/{key}")

@router.post("/redirect/{platform}/{UUID_id}")
async def redirect_route(request: Request, response: Response, platform: str, UUID_id: str, db: Session = Depends(get_db)):
    set_cors_allow_all(response)

    # choose base destination
    if platform == "pridecons":
        base = f"https://pridecons.com/web/download_agreement/{UUID_id}"
    elif platform == "service":
        base = f"https://service.pridecons.sbs/kyc/agreement/{UUID_id}"
    else:
        base = f"https://pridebuzz.in/kyc/agreement/{UUID_id}"

    # forward all incoming query params to destination (e.g., ?action=gateway-error&reason=...)
    qp = request.query_params  # type: QueryParams
    redirect_url = _append_query(base, qp)

    # record step + any error meta if present
    kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == UUID_id).first()
    if kyc_user:
        kyc_user.step_third = True
        # if caller sent an error/action, keep it for audit/UX
        if "action" in qp or "error" in qp or "reason" in qp:
            details = dict(qp)
            try:
                # keep previous error context if exists
                old = kyc_user.faild_error or ""
                merged = {"prev": old} if old else {}
                merged.update(details)
                kyc_user.faild_error = json.dumps(merged)
            except Exception:
                # fallback to simple string
                kyc_user.faild_error = str(details)
        db.commit()

    return RedirectResponse(url=redirect_url, status_code=302)

@router.post("/response_url/{UUID_id}")
async def response_url_endpoint(request: Request,response: Response,UUID_id: str,db: Session = Depends(get_db)):
    set_cors_allow_all(response)
    payload = await request.json()
    result = payload.get("result")
    document = result.get("document")
    signed_url = document.get("signed_url")
    try:
        async with httpx.AsyncClient() as client:
            pdf_response = await client.get(signed_url)
        pdf_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"HTTP error fetching PDF: {exc}"
        )
    
    await write_json_to_s3(payload, f"esign_response/{UUID_id}.json")

    kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == UUID_id).first()

    key = f"kyc_documents/{UUID_id}.pdf"
    await write_pdf_to_s3(pdf_response.content,key)
    await send_agreement(kyc_user.email,kyc_user.full_name,pdf_response.content)

    # ✅ Convert PDF to Base64 and save in DB
    base64_pdf = base64.b64encode(pdf_response.content).decode('utf-8')
    kyc_user.complete_signature_url = base64_pdf

    kyc_user.step_four = True
    db.commit()

    print("✅ Zoop callback received:")
    print(payload)
    return {"status": "received"}


@router.post("/redirect")
async def redirect_route(response: Response,UUID_id: str):
    set_cors_allow_all(response)
    redirect_url = f"https://pridebuzz.in/kyc/agreement/{UUID_id}"
    return RedirectResponse(
        url=redirect_url, 
        status_code=302
    )

@router.post("/settlement-redirect/{UUID_id}")
async def redirect_route(response: Response,UUID_id: str):
    set_cors_allow_all(response)
    url = f"https://pridebuzz.in/crm/settlement/{UUID_id}"
    return RedirectResponse(
        url=url, 
        status_code=302
    )

@router.post("/e-stamp/response_url/{UUID_id}")
async def response_url_endpoint(request: Request,response: Response,UUID_id: str,db: Session = Depends(get_db)):
    set_cors_allow_all(response)
    payload = await request.json()
    result = payload.get("result")
    estamp = result.get("estamp")
    documentUrl = estamp.get("documentUrl")
    await write_json_to_s3(payload, f"estamp_response/{UUID_id}.json")
    await init_estamp(documentUrl,UUID_id,db)
    # print("✅ Zoop callback received:")
    # print(payload)
    return {"status": "received"}

@router.post("/e-sign/response_url/{UUID_id}")
async def response_url_endpoint(request: Request,response: Response,UUID_id: str,db: Session = Depends(get_db)):
    set_cors_allow_all(response)
    payload = await request.json()
    result = payload.get("result")
    document = result.get("document")
    signed_url = document.get("signed_url")
    try:
        async with httpx.AsyncClient() as client:
            pdf_response = await client.get(signed_url)
        pdf_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"HTTP error fetching PDF: {exc}"
        )
    key = f"settlement/{UUID_id}.pdf"
    await write_pdf_to_s3(pdf_response.content,key)
    EStampUser = db.query(EStamp).filter(EStamp.UUID_id == UUID_id).first()
    EStampUser.file = key
    await Final_send_agreement(EStampUser.recepient_email, EStampUser.second_party_name,EStampUser.mail_subject, EStampUser.mail_body, pdf_response.content )
    db.commit()
    db.refresh(EStampUser)
    
    # print("✅ Zoop callback received:")
    # print(payload)
    return {"status": "received"}



from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import APIRouter, Request, HTTPException, Depends, Response
import aioboto3
from config import AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION
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
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
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
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    ) as s3_client:
        await s3_client.put_object(
            Bucket=S3_BUCKET_NAME,  # Use the actual bucket name
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf"  # Correct MIME type for PDF
        )
    
    print(f"✅ Uploaded {key} to s3://{S3_BUCKET_NAME}/{key}")

@router.post("/redirect/{platform}/{UUID_id}")
async def redirect_route(response: Response,platform: str, UUID_id: str, db: Session = Depends(get_db)):
    set_cors_allow_all(response)
    if platform == "pridecons":
        redirect_url = f"https://pridecons.com/web/download_agreement/{UUID_id}"
    else:
        redirect_url = f"https://pridebuzz.in/kyc/agreement/{UUID_id}"

    kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == UUID_id).first()
    kyc_user.step_third = True
    db.commit()
    return RedirectResponse(
        url=redirect_url,
        status_code=302
    )

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



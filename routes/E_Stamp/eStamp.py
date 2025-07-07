import os
import base64
import requests
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from db.connection import get_db
from db.models import EStamp
import httpx
import uuid
import tempfile
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers, PdfSignatureMetadata
from pyhanko.sign.fields import SigFieldSpec
import asyncio
from config import PAN_API_ID, PAN_API_KEY
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO, StringIO
from reportlab.pdfgen import canvas
from reportlab.pdfgen import canvas as rl_canvas
from routes.E_Stamp.kyc_mail import send_agreement
from typing import Any, Dict, Optional

router = APIRouter(tags=["E-Stamp"])

ESTAMP_API_URL = os.getenv("ESTAMP_API_URL", "https://test.zoop.one/contract/estamp")
APP_ID          = os.getenv("ESTAMP_APP_ID", "67d16e2526e9ce0028198abe")
API_KEY         = os.getenv("ESTAMP_API_KEY", "3RX0JDP-46XMCQT-JCGD2TF-4PJ5GT9")

async def request_with_retry(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    retries: int = 3,
    backoff_factor: float = 0.5,
) -> Any:
    """
    Generic HTTP request with automatic retry on failures.

    - retries: कुल कितनी बार कोशिश करनी है (default 3)
    - backoff_factor: पहले retry से पहले कितनी देर रुके (seconds), फिर doubling होगी
    """
    last_exc: Optional[Exception] = None

    async with httpx.AsyncClient() as client:
        for attempt in range(1, retries + 1):
            try:
                response = await client.request(
                    method, url, headers=headers, json=json, params=params
                )
                # status 4xx/5xx के लिए exception
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # अगर client-side error (4xx), तो retry नहीं करना
                if 400 <= status < 500:
                    raise HTTPException(
                        status_code=status,
                        detail=f"API returned client error {status}: {exc.response.text}"
                    )
                last_exc = exc

            except (httpx.ReadError, httpx.RequestError) as exc:
                # network या timeout error
                last_exc = exc

            # अभी तक success नहीं हुआ, तो retry करने से पहले wait करें
            if attempt < retries:
                wait_time = backoff_factor * (2 ** (attempt - 1))
                await asyncio.sleep(wait_time)

    # सारे प्रयास fail हुए
    raise HTTPException(
        status_code=500,
        detail=f"API request failed after {retries} attempts: {last_exc}"
    )


async def sign_pdf(pdf_bytes: bytes) -> bytes:
    """
    Sign the PDF bytes using the certificate and return the signed PDF bytes.
    """
    try:
        # Save the PDF bytes to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        signed_pdf_path = tmp_path + "_signed.pdf"

        def sign_pdf_sync():
            # Load the signing certificate (PKCS#12 file)
            signer = signers.SimpleSigner.load_pkcs12(
                pfx_file='./certificate.pfx', 
                passphrase=b'123456'  # Update your passphrase
            )
            with open(tmp_path, 'rb') as doc:
                writer = IncrementalPdfFileWriter(doc, strict=False)

                sig_field_spec = SigFieldSpec(
                    'Signature1',
                    on_page=-1,
                    box=(100, 100, 250, 50)
                )

                # (left, bottom, right, top)

                signed_pdf_io = signers.sign_pdf(
                    writer,
                    signature_meta=PdfSignatureMetadata(field_name='Signature1'),
                    signer=signer,
                    existing_fields_only=False, 
                    new_field_spec=sig_field_spec
                )

            with open(signed_pdf_path, 'wb') as outf:
                outf.write(signed_pdf_io.getvalue())

            return signed_pdf_path

        result = await asyncio.to_thread(sign_pdf_sync)
        os.remove(tmp_path)

        with open(result, "rb") as f:
            signed_pdf_bytes = f.read()
        os.remove(result)
        return signed_pdf_bytes

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def create_header_overlay(page_width: float, page_height: float, pride_logo_path: str, cin: str, mail: str, call: str):
    """
    Create an overlay PDF page containing the header.
    - Top left: pride logo
    - Top right: CIN, email, and call details (one per line)
    """
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Draw the pride logo on the top left
    # Adjust logo dimensions as needed
    logo_width = 140  
    logo_height = 40  
    # Position: 40 pts from left, 20 pts from top (adjusting for logo height)
    c.drawImage(pride_logo_path, 40, page_height - logo_height - 20, width=logo_width, height=logo_height)
    
    # Draw the CIN, email, and call details on the top right
    header_details = [cin, mail, call]
    c.setFont("Helvetica", 10)
    margin = 40  # margin from right edge
    line_height = 12  # vertical space between lines
    
    # Start from the top with some padding (20 pts from the top)
    text_y = page_height - 20 - line_height
    for line in header_details:
        # text_width = c.stringWidth(line, "Helvetica", 10)
        c.drawString(page_width - 160 - margin, text_y, line)
        text_y -= line_height
    c.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]

def create_footer_overlay(page_width: float, page_height: float, page_num: int):
    """
    Create an overlay PDF page containing the footer.
    - Left bottom: page number ("Page X")
    - Right bottom: fixed footer text
    """
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    c.setFont("Helvetica", 10)
    
    # Draw the page number at bottom left (40 points from left, 20 points from bottom)
    c.drawString(40, 20, f"Page {page_num}")
    
    # Draw the footer text at bottom right
    footer_text = "©Service Agreement of Pride Trading Consultancy Pvt. Ltd."
    text_width = c.stringWidth(footer_text, "Helvetica", 10)
    c.drawString(page_width - text_width - 40, 20, footer_text)
    
    c.save()
    packet.seek(0)
    # Return the first (and only) page of the generated overlay PDF
    return PdfReader(packet).pages[0]

def create_watermark_overlay(page_width: float, page_height: float, text: str):
    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(page_width, page_height))
    c.setFont("Helvetica-Bold", 38)
    c.setFillColorRGB(0.8, 0.8, 0.8, alpha=0.2)  # light gray with some transparency

    # Save the current state before rotating
    c.saveState()
    
    # Rotate and translate (this centers the text)
    c.translate(page_width / 2, page_height / 2)
    c.rotate(45)  # 270 degrees rotation
    
    # Draw the watermark centered
    c.drawCentredString(0, 0, text)

    c.restoreState()
    c.save()
    buffer.seek(0)

    return PdfReader(buffer).pages[0]

@router.post("/e-stamp")
async def init_estamp(
    firstPartyName:     str        = Form(...),
    secondPartyName:    str        = Form(...),
    stampDutyPaidBy:    str        = Form(...),
    stampDutyValue:     str        = Form(...),
    purposeOfStampDuty: str | None = Form(None),
    articleId:          str        = Form(...),
    considerationPrice: str        = Form(...),
    branchId:           str        = Form(...),
    recepientEmail:     str | None = Form(None),
    file:               UploadFile = File(None),
    mailSubject:        str        = Form(...),
    mailBody:           str        = Form(...),
    mobile:             str        = Form(...),
    city:               str        = Form(...),
    pan:                str        = Form(...),
    db:                 Session    = Depends(get_db),
):
    generated_uuid = str(uuid.uuid4())
    """
    Initiate an e-Stamp transaction by either uploading a file (when procure=False) 
    or simply requesting procurement from Zoop (when procure=True).
    """

    # Prepare request files if file is provided and procure is False
    files = {}
    if file :
        file_contents = await file.read()
        files["file"] = (file.filename, file_contents, file.content_type)
    
    # Build the data payload for the external API
    data = {
        "firstPartyName":     firstPartyName,
        "secondPartyName":    secondPartyName,
        "stampDutyPaidBy":    stampDutyPaidBy,
        "stampDutyValue":     stampDutyValue,
        "purposeOfStampDuty": purposeOfStampDuty,
        "articleId":          articleId,
        "considerationPrice": considerationPrice,
        "branchId":           branchId,
        "responseUrl":        f"https://pridecons.sbs/e-stamp/response_url/{generated_uuid}",
        "recepientEmail":     recepientEmail,
    }

    # Save the request data in your DB for future reference
    new_estamp = EStamp(
        UUID_id=generated_uuid,
        first_party_name=firstPartyName,
        second_party_name=secondPartyName,
        stamp_duty_paid_by=stampDutyPaidBy,
        stamp_duty_value=stampDutyValue,
        purpose_of_stamp_duty=purposeOfStampDuty,
        article_id=articleId,
        consideration_price=considerationPrice,
        branch_id=branchId,
        procure=False,
        recepient_email=recepientEmail,
        mail_subject=mailSubject,
        mail_body=mailBody,
        mobile=mobile,
        city=city,
        pan=pan,
        file=None  # If you want to store file details or path, modify accordingly
    )
    try:
        db.add(new_estamp)
        db.commit()
        db.refresh(new_estamp)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    # Set headers for the external API call
    headers = {
        "app-id": "67d16e2526e9ce0028198abe",
        "api-key": "3RX0JDP-46XMCQT-JCGD2TF-4PJ5GT9",
    }
    
    # Endpoint for the Zoop e-stamp init
    url = "https://test.zoop.one/contract/estamp/v1/init"
    print("data : ",data)
    
    try:
        response = requests.post(url, headers=headers, data=data, files=files)
        
        # Check if the request was successful
        if response.status_code == 200:
            api_response = response.json()
            
            # Optionally, update your DB record with any relevant response data
            new_estamp.transaction_id = api_response.get("transaction_id")
            db.commit()
            
            return JSONResponse(
                status_code=200, 
                content={
                    "status": "success",
                    "data": api_response,
                    "message": "E-stamp initiation successful."
                },
            )
        else:
            # Log or raise error if the external API call fails
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Zoop e-Stamp API error: {response.text}",
            )
    
    except Exception as e:
        # Catch any unexpected exceptions (network issues, timeouts, etc.)
        raise HTTPException(
            status_code=500, 
            detail=f"Error calling Zoop e-Stamp API: {e}",
        )
    
@router.get("/e-stamp/articles")
async def getArticles(branch):
    headers = {
            "app-id":  APP_ID,
            "api-key": API_KEY,
    }

    async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ESTAMP_API_URL}/v1/fetch/articles?branch={branch}",
                headers=headers
            )

    # forward errors
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.text
        )

    # return the JSON from the eStamp API directly
    return JSONResponse(status_code=resp.status_code, content=resp.json())

@router.get("/e-stamp/branches")
async def getArticles():
    headers = {
            "app-id":  APP_ID,
            "api-key": API_KEY,
    }

    async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ESTAMP_API_URL}/v1/fetch/branches",
                headers=headers
            )

    # forward errors
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.text
        )

    # return the JSON from the eStamp API directly
    return JSONResponse(status_code=resp.status_code, content=resp.json())

@router.post("/settlement-esign")
async def init_estamp(
    secondPartyName:    str        = Form(None),
    purposeOfStampDuty: str | None = Form(None),
    recepientEmail:     str | None = Form(None),
    file:               UploadFile = File(None),
    mailSubject:        str        = Form(None),
    mailBody:           str        = Form(None),
    mobile:             str        = Form(None),
    city:               str        = Form(None),
    pan:                str        = Form(None),
    db:                 Session    = Depends(get_db),
):
    generated_uuid = str(uuid.uuid4())
    """
    Initiate an e-Stamp transaction by either uploading a file (when procure=False) 
    or simply requesting procurement from Zoop (when procure=True).
    """

    # Prepare request files if file is provided and procure is False
    if file:
        file_contents = await file.read()
        # Directly use file_contents to create a BytesIO stream
        pdf_stream = BytesIO(file_contents)
        overlay_pdf = PdfReader(pdf_stream)
    else:
        raise HTTPException(status_code=400, detail="No file provided.")

    

    # Save the request data in your DB for future reference
    new_estamp = EStamp(
        UUID_id=generated_uuid,
        second_party_name=secondPartyName,
        purpose_of_stamp_duty=purposeOfStampDuty,
        procure=False,
        recepient_email=recepientEmail,
        mobile=mobile,
        mail_subject=mailSubject,
        mail_body=mailBody,
        city=city,
        pan=pan,
        file=None,  # If you want to store file details or path, modify accordingly
        first_party_name="",
        stamp_duty_paid_by="",
        stamp_duty_value="",
        article_id="",
        consideration_price="",
        branch_id="",
    )
    try:
        db.add(new_estamp)
        db.commit()
        db.refresh(new_estamp)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
    # Define the assets and details for the header overlay
    pride_logo = "logo/pride-logo1.png"
    cin = "CIN: U67190GJ2022PTC130684"
    mail = "Mail:- compliance@pridecons.com"
    call = "Call:- +91-8141054547"
        
    # Create a PdfWriter object and add each page after overlaying the header, watermark, and footer
    output_pdf = PdfWriter()
    watermark_text = "Pride Trading Consultancy Private Limited"

    for i, page in enumerate(overlay_pdf.pages, start=1):
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        
        # Create and merge header overlay
        header_overlay = create_header_overlay(page_width, page_height, pride_logo, cin, mail, call)
        page.merge_page(header_overlay)
        
        # Create and merge watermark overlay
        watermark_overlay = create_watermark_overlay(page_width, page_height, watermark_text)
        page.merge_page(watermark_overlay)

        # Create and merge footer overlay
        footer_overlay = create_footer_overlay(page_width, page_height, i)
        page.merge_page(footer_overlay)

        output_pdf.add_page(page)

    output_path = "routes/kyc_service/final_merged.pdf"
    with open(output_path, "wb") as f:
        output_pdf.write(f)

    with open(output_path, "rb") as pdf_file:
        final_pdf_bytes = pdf_file.read()
    
    signed_pdf_bytes = await sign_pdf(final_pdf_bytes)
    pdf_base64 = base64.b64encode(signed_pdf_bytes).decode("utf-8")
    
    signers = {
                "signer_name": secondPartyName,
                "signer_email": recepientEmail,
                "signer_city": city,
                "signer_purpose": purposeOfStampDuty,
                "sign_coordinates": [
                    {
                        "page_num": 0,
                        "x_coord": 40,
                        "y_coord": 50
                    }
                ]
    }

    url = "https://live.zoop.one/contract/esign/v5/init"
    headers = {
                "app-id": PAN_API_ID,
                "api-key": PAN_API_KEY,
                "Content-Type": "application/json",
            }

    payload = {
                "document": {
                    "name": "Agreement Esigning",
                    "data": pdf_base64,
                    "info": "test"
                },
                "signers": [signers],
                "txn_expiry_min": "10080",
                "white_label": "N",
                "redirect_url": f"https://pridecons.sbs/settlement-redirect/{generated_uuid}",
                "response_url": f"https://pridecons.sbs/e-sign/response_url/{generated_uuid}",
                "esign_type": "AADHAAR",
                "email_template": {
                    "org_name": "Pride Trading Consultancy"
                }
            }
    print("payload : ",payload)

    data = await request_with_retry(
        method="POST",
        url=url,
        headers=headers,
        json=payload,
        retries=50,
        backoff_factor=0.5,
    )
    requests_data=data.get("requests")[0]
    signing_url=requests_data.get("signing_url")

    await send_agreement(recepientEmail, secondPartyName, signing_url)

    return signing_url
    
@router.get("/settlement-esign")
async def get_stamp(db: Session = Depends(get_db)):
    kyc_users = db.query(EStamp).all()
    result = [user.__dict__ for user in kyc_users]
    for item in result:
        item.pop("_sa_instance_state", None)  # Remove SQLAlchemy internal field
    return result
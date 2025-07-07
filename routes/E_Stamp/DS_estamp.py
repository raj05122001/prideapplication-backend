import os
import base64
import requests
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from db.connection import get_db
from db.models import EStamp
import asyncio
from reportlab.pdfgen import canvas
from reportlab.pdfgen import canvas as rl_canvas
import tempfile
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers, PdfSignatureMetadata
from pyhanko.sign.fields import SigFieldSpec
from config import PAN_API_ID, PAN_API_KEY
import httpx
from routes.E_Stamp.kyc_mail import send_agreement

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
                    on_page=0,
                    box=(340, 160, 490, 110)
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

async def init_estamp(documentUrl: str,UUID_id:str, db: Session = Depends(get_db)):
    """
    Initiate an e-Stamp transaction by either uploading a file (when procure=False) 
    or simply requesting procurement from Zoop (when procure=True).
    """    
    EStampUser = db.query(EStamp).filter(EStamp.UUID_id == UUID_id).first()
    try:       
        if documentUrl:
            print("api_response : ",documentUrl)
            documentResponse = requests.get(documentUrl)
            if documentResponse.status_code == 200:
                # 2. Get the raw bytes from the file
                file_content = documentResponse.content

                # 3. Write to a local file, or do something else with the bytes
                with open("document.pdf", "wb") as f:
                    f.write(file_content)
            
            signed_pdf_bytes = await sign_pdf(file_content)
            pdf_base64 = base64.b64encode(signed_pdf_bytes).decode("utf-8")
    
            signers = {
                "signer_name": EStampUser.second_party_name,
                "signer_email": EStampUser.recepient_email,
                "signer_city": EStampUser.city,
                "signer_purpose": EStampUser.purpose_of_stamp_duty,
                "sign_coordinates": [
                    {
                        "page_num": 0,
                        "x_coord": 350,
                        "y_coord": 100
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
                "redirect_url": f"https://pridecons.sbs/settlement-redirect/{EStampUser.UUID_id}",
                "response_url": f"https://pridecons.sbs/e-sign/response_url/{EStampUser.UUID_id}",
                "esign_type": "AADHAAR",
                "email_template": {
                    "org_name": "Pride Trading Consultancy"
                }
            }

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, headers=headers, json=payload)
                # Check for 4xx/5xx errors; response.raise_for_status() will raise an HTTPStatusError if found.
                response.raise_for_status()
            except httpx.ReadError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Read error calling Zoop API: {exc}"
                )
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=f"Zoop API returned an error: {exc.response.text}"
                )
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"HTTP error calling Zoop API: {exc}"
                )
            data = response.json()
            requests_data=data.get("requests")[0]
            signing_url=requests_data.get("signing_url")
            await send_agreement(EStampUser.recepient_email, EStampUser.second_party_name, signing_url)

    except Exception as e:
        # Catch any unexpected exceptions (network issues, timeouts, etc.)
        print(e)

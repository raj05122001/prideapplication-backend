import os
import uuid
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Query
from sqlalchemy.orm import Session
from db.models import KYCUser
from db.connection import get_db
from routes.otp_service.otp_service import send_otp_kyc, verify_otp
from db.schema import KYCOTPRequest, KYCOTPVerifyRequest, KYCDetails
from routes.kyc_service.agreement_kyc_pdf import generate_kyc_pdf
from config import CF_R2_ACCESS_KEY_ID, CF_R2_ACCOUNT_ID, CF_R2_REGION, CF_R2_SECRET_ACCESS_KEY
import aioboto3
import pytz
import logging
from logging.handlers import RotatingFileHandler

from typing import Dict, Any, List, Tuple, Optional

# -----------------------
# Logger Configuration
# -----------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("kyc")
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(
    filename=os.path.join(LOG_DIR, "kyc_errors.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# -----------------------
# Router Initialization
# -----------------------
router = APIRouter(tags=["Agreement KYC"])

# -----------------------
# AWS S3 Upload Utility
# -----------------------
S3_BUCKET_NAME = "pride-user-data"

async def write_pdf_to_s3(pdf_bytes: bytes, key: str):
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
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
    logger.info(f"Uploaded PDF to s3://{S3_BUCKET_NAME}/{key}")

# Ensure upload directories exist
USER_IMAGE_UPLOAD_DIR = "static/kyc/Users_Images"
os.makedirs(USER_IMAGE_UPLOAD_DIR, exist_ok=True)

# -----------------------
# OTP Endpoints
# -----------------------
@router.post("/kyc_otp")
async def kyc_send_otp(
    request: KYCOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    tracking_id = await send_otp_kyc(request.mobile, background_tasks, db, request.email)
    return {"message": f"OTP sent to {request.mobile}", "tracking_id": tracking_id}

@router.post("/kyc_otp/verify")
def kyc_verify_otp(request: KYCOTPVerifyRequest, db: Session = Depends(get_db)):
    result = verify_otp(request.mobile, request.otp, db)
    if result.get("status") == "success" and result.get("status_code") == 200:
        new_uuid = str(uuid.uuid4())
        kyc_user = KYCUser(mobile=request.mobile, email=request.email, UUID_id=new_uuid, step_first=True)
        db.add(kyc_user)
        db.commit()
        db.refresh(kyc_user)
        return {"message": "OTP verified successfully", "UUID_id": new_uuid}
    raise HTTPException(status_code=400, detail="Invalid OTP")

# -----------------------
# KYC Details Update
# -----------------------
@router.post("/kyc_user_details")
async def update_kyc_details(
    UUID_id: str = Form(...),
    full_name: str = Form(None),
    father_name: str = Form(None),
    alternate_mobile: str = Form(None),
    dob: date = Form(None),
    age: int = Form(None),
    nationality: str = Form(None),
    pan_no: str = Form(...),
    aadhaar_no: str = Form(None),
    gender: str = Form(None),
    marital_status: str = Form(None),
    state: str = Form(None),
    city: str = Form(None),
    address: str = Form(None),
    pin_code: str = Form(None),
    occupation: str = Form(None),
    director_name: str = Form(None),
    gst_no: str = Form(None),
    platform: str = Form(None),
    user_image: UploadFile = File(None),
    gst_pdf: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    try:
        # Fetch existing record
        kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == UUID_id).first()
        if not kyc_user:
            raise HTTPException(status_code=404, detail="KYC record not found")

        # Update fields
        for field, value in {
            'full_name': full_name,
            'father_name': father_name,
            'alternate_mobile': alternate_mobile,
            'dob': dob,
            'age': age,
            'nationality': nationality,
            'pan_no': pan_no,
            'aadhaar_no': aadhaar_no,
            'gender': gender,
            'marital_status': marital_status,
            'state': state,
            'city': city,
            'address': address,
            'pin_code': pin_code,
            'occupation': occupation,
            'director_name': director_name,
            'gst_no': gst_no,
        }.items():
            setattr(kyc_user, field, value)

        # Handle GST PDF upload
        if gst_pdf:
            key = f"gstPdf/{UUID_id}.pdf"
            pdf_bytes = await gst_pdf.read()
            try:
                await write_pdf_to_s3(pdf_bytes, key)
                kyc_user.gst_pdf = key
            except Exception:
                logger.exception("Failed to upload GST PDF for UUID %s", UUID_id)
                raise HTTPException(500, detail="Failed to upload GST PDF")

        # Image upload helper
        async def process_image_upload(image_file: UploadFile, upload_dir: str, existing_path: str = None) -> str:
            if image_file:
                if not image_file.content_type.startswith("image/"):
                    raise HTTPException(status_code=400, detail="Please upload a valid image")
                if existing_path and os.path.exists(existing_path):
                    os.remove(existing_path)
                ext = image_file.filename.rsplit('.', 1)[-1]
                filename = f"{uuid.uuid4()}.{ext}"
                path = os.path.join(upload_dir, filename)
                with open(path, 'wb') as f:
                    f.write(await image_file.read())
                return path
            return existing_path

        # Upload user image
        kyc_user.user_image = await process_image_upload(user_image, USER_IMAGE_UPLOAD_DIR, kyc_user.user_image)

        # Prepare data for PDF generation
        india_tz = pytz.timezone('Asia/Kolkata')
        now_str = datetime.now(india_tz).strftime("%d-%b-%Y %H:%M:%S")
        data = {
            'full_name': full_name,
            'father_name': father_name,
            'address': address,
            'date': now_str,
            'email': kyc_user.email,
            'city': city,
            'UUID_id': UUID_id,
            'platform': platform,
        }

        # Generate and sign PDF
        try:
            signer_details = await generate_kyc_pdf(data, UUID_id, db)
        except Exception:
            logger.exception("PDF generation or e-sign failed for UUID %s", UUID_id)
            raise HTTPException(500, detail="Failed while generating or signing PDF")

        # Store signer info
        kyc_user.group_id = signer_details.get('group_id')
        reqs = signer_details.get('requests', [])
        kyc_user.signature_url = reqs[0].get('signing_url') if reqs and isinstance(reqs, list) and 'signing_url' in reqs[0] else None
        kyc_user.step_second = True

        db.commit()
        db.refresh(kyc_user)

        return {
            'message': 'KYC details updated successfully',
            'UUID_id': kyc_user.UUID_id,
            'signer_details': signer_details,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled exception in update_kyc_details for UUID %s", UUID_id)
        raise HTTPException(status_code=500, detail="Internal server error")

# -----------------------
# Retrieval Endpoints
# -----------------------
@router.get("/kyc/{uuid_id}", response_model=KYCDetails)
def get_kyc_details(uuid_id: str, db: Session = Depends(get_db)):
    kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == uuid_id).first()
    if not kyc_user:
        raise HTTPException(status_code=404, detail="KYC record not found")
    return kyc_user

from pydantic import BaseModel, EmailStr
from typing import Optional, List
import io
import pandas as pd
from fastapi.responses import StreamingResponse

class KYCPage(BaseModel):
    items: List[KYCDetails]
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_prev: bool



from fastapi import Query
from sqlalchemy import or_, func

SAFE_SORT_MAP = {
    "id": KYCUser.id,
    "mobile": KYCUser.mobile,
    "email": KYCUser.email,
    "pan_no": KYCUser.pan_no,
    "dob": KYCUser.dob,
}

@router.get("/kyc", response_model=KYCPage)
def list_kyc_details(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    q: Optional[str] = Query(
        None, description="Search across mobile, email, pan_no (partial, case-insensitive)"
    ),
    mobile: Optional[str] = Query(None, description="Filter by mobile (partial)"),
    email: Optional[str] = Query(None, description="Filter by email (partial)"),
    pan_no: Optional[str] = Query(None, description="Filter by PAN (partial)"),
    sort_by: str = Query("id", description=f"One of: {', '.join(SAFE_SORT_MAP.keys())}"),
    order: str = Query("desc", regex="^(asc|desc)$"),
):
    query = db.query(KYCUser)

    # --- flexible search ---
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(
            KYCUser.mobile.ilike(like),
            KYCUser.email.ilike(like),
            KYCUser.pan_no.ilike(like),
        ))

    if mobile:
        filters.append(KYCUser.mobile.ilike(f"%{mobile.strip()}%"))
    if email:
        filters.append(KYCUser.email.ilike(f"%{email.strip()}%"))
    if pan_no:
        filters.append(KYCUser.pan_no.ilike(f"%{pan_no.strip()}%"))

    if filters:
        query = query.filter(*filters)

    # --- total before pagination ---
    total = query.count()

    # --- safe sorting ---
    sort_col = SAFE_SORT_MAP.get(sort_by, KYCUser.id)
    if order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # --- pagination ---
    offset = (page - 1) * limit
    rows = query.offset(offset).limit(limit).all()

    # --- build response ---
    pages = (total + limit - 1) // limit if limit else 1
    return KYCPage(
        items=[KYCDetails.model_validate(r.__dict__) for r in rows],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )

@router.get("/kyc/export")
def export_kyc_details(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(
        None, description="Search across mobile, email, pan_no (partial, case-insensitive)"
    ),
    mobile: Optional[str] = Query(None, description="Filter by mobile (partial)"),
    email: Optional[str] = Query(None, description="Filter by email (partial)"),
    pan_no: Optional[str] = Query(None, description="Filter by PAN (partial)"),
    sort_by: str = Query("id", description=f"One of: {', '.join(SAFE_SORT_MAP.keys())}"),
    order: str = Query("desc", regex="^(asc|desc)$"),
):
    """
    Export all matching KYC records as an XLSX file.
    Same filters & sorting as /kyc, but NO pagination.
    """
    query = db.query(KYCUser)

    # --- same flexible search as /kyc ---
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(
            KYCUser.mobile.ilike(like),
            KYCUser.email.ilike(like),
            KYCUser.pan_no.ilike(like),
        ))

    if mobile:
        filters.append(KYCUser.mobile.ilike(f"%{mobile.strip()}%"))
    if email:
        filters.append(KYCUser.email.ilike(f"%{email.strip()}%"))
    if pan_no:
        filters.append(KYCUser.pan_no.ilike(f"%{pan_no.strip()}%"))

    if filters:
        query = query.filter(*filters)

    # --- safe sorting (same as /kyc) ---
    sort_col = SAFE_SORT_MAP.get(sort_by, KYCUser.id)
    if order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    rows = query.all()

    # Pydantic schema से dict बनाएं ताकि fields clean रहें
    records = [KYCDetails.model_validate(r.__dict__).model_dump() for r in rows]

    # DataFrame → Excel in memory
    df = pd.DataFrame(records)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="KYC")
    output.seek(0)

    filename = f"kyc_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )



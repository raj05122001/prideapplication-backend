import os
import uuid
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from db.models import KYCUser
from db.connection import get_db
from routes.otp_service.otp_service import send_otp_kyc, verify_otp
from db.schema import KYCOTPRequest, KYCOTPVerifyRequest, KYCDetails
from routes.kyc_service.agreement_kyc_pdf import generate_kyc_pdf
from config import AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION
import aioboto3
import pytz

router = APIRouter(tags=["Agreement KYC"])

S3_BUCKET_NAME="pride-user-data"

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


USER_IMAGE_UPLOAD_DIR = "static/kyc/Users_Images"
for directory in [USER_IMAGE_UPLOAD_DIR]:
    os.makedirs(directory, exist_ok=True)

@router.post("/kyc_otp")
async def kyc_send_otp(request: KYCOTPRequest,background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    tracking_id = await send_otp_kyc(request.mobile, background_tasks, db, request.email)
    return {"message": f"OTP sent to {request.mobile}", "tracking_id": tracking_id}

@router.post("/kyc_otp/verify")
def kyc_verify_otp(request: KYCOTPVerifyRequest, db: Session = Depends(get_db)):
    otp_verification_result = verify_otp(request.mobile, request.otp, db)
    if otp_verification_result["status"] == "success" and otp_verification_result["status_code"] == 200:
        generated_uuid = str(uuid.uuid4())
        kyc_user = KYCUser(mobile=request.mobile, email=request.email, UUID_id=generated_uuid,step_first=True)
        db.add(kyc_user)
        db.commit()
        db.refresh(kyc_user)
        return {"message": "OTP verified successfully", "UUID_id": generated_uuid}
    else:
        raise HTTPException(status_code=400, detail="Invalid OTP")

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
    """
    Updates the KYC record with complete user details and processes image uploads.
    The UUID_id generated during OTP verification is used to locate the record.
    """
    kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == UUID_id).first()
    if not kyc_user:
        raise HTTPException(status_code=404, detail="KYC record not found")

    kyc_user.full_name = full_name
    kyc_user.father_name = father_name
    kyc_user.alternate_mobile = alternate_mobile
    kyc_user.dob = dob
    kyc_user.age = age
    kyc_user.nationality = nationality
    kyc_user.pan_no = pan_no
    kyc_user.aadhaar_no = aadhaar_no
    kyc_user.gender = gender
    kyc_user.marital_status = marital_status
    kyc_user.state = state
    kyc_user.city = city
    kyc_user.address = address
    kyc_user.pin_code = pin_code
    kyc_user.occupation = occupation
    kyc_user.director_name = director_name
    kyc_user.gst_no = gst_no

    if gst_pdf:
        key = f"gstPdf/{UUID_id}.pdf"
        pdf_bytes = await gst_pdf.read()  # 🔥 read content from UploadFile
        await write_pdf_to_s3(pdf_bytes, key)  # 🔥 pass bytes, not UploadFile
        kyc_user.gst_pdf = key


    async def process_image_upload(image_file: UploadFile, upload_dir: str, existing_path: str = None) -> str:
        if image_file:
            if not image_file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Please upload a valid image")
            if existing_path and os.path.exists(existing_path):
                os.remove(existing_path)
            file_ext = image_file.filename.split(".")[-1]
            unique_filename = f"{uuid.uuid4()}.{file_ext}"
            file_path = os.path.join(upload_dir, unique_filename)
            with open(file_path, "wb") as f:
                f.write(await image_file.read())
            return file_path
        return existing_path

    # Use current date and retrieve the email from the kyc_user record
    # current_date_str = datetime.now()
    india_timezone = pytz.timezone('Asia/Kolkata')
    now_in_india = datetime.now(india_timezone)
    data = {
        "full_name": full_name,
        "father_name": father_name,
        "address": address,
        "date": now_in_india,      # automatically current date and time
        "email": kyc_user.email,         # email from the database
        "city": city,
        "UUID_id":UUID_id,
        "platform":platform
    }

    kyc_user.user_image = await process_image_upload(user_image, USER_IMAGE_UPLOAD_DIR, kyc_user.user_image)
    
    signer_details = await generate_kyc_pdf(data,UUID_id,db)

    kyc_user.group_id=signer_details.get("group_id")
    requests_list = signer_details.get("requests", [])
    if requests_list and isinstance(requests_list, list) and "signing_url" in requests_list[0]:
        kyc_user.signature_url = requests_list[0]["signing_url"]
    else:
        kyc_user.signature_url = None

    kyc_user.step_second = True

    db.commit()
    db.refresh(kyc_user)
    return {
        "message": "KYC details updated successfully",
        "UUID_id": kyc_user.UUID_id,
        "signer_details": signer_details
    }

@router.get("/kyc/{uuid_id}", response_model=KYCDetails)
def get_kyc_details(uuid_id: str, db: Session = Depends(get_db)):
    kyc_user = db.query(KYCUser).filter(KYCUser.UUID_id == uuid_id).first()
    if not kyc_user:
        raise HTTPException(status_code=404, detail="KYC record not found")
    return kyc_user

@router.get("/kyc", response_model=list[KYCDetails])
def get_kyc_details(db: Session = Depends(get_db)):
    kyc_users = db.query(KYCUser).all()
    print("kyc_users : ",kyc_users)  # 👈 Check this
    return kyc_users

from sqlalchemy import Column, Integer, String, JSON, DateTime,func, ARRAY, Text, ForeignKey,Float, Date, Boolean
from db.connection import Base
from datetime import datetime
from sqlalchemy.orm import relationship, declarative_base
import uuid
import pytz

class OTP(Base):
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String(20), nullable=False, index=True)
    otp = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class UserDetails(Base):
    __tablename__ = "user_details"
    
    # Use phone number as the primary key.
    phone_number = Column(String(10), primary_key=True, unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)  # Hashed password storage.
    role = Column(String(10), default="user", nullable=False)  # Default role is 'user'.
    service = Column(ARRAY(String(100)), nullable=False, default=list)
    service_active_date = Column(String(100), nullable=True, default=None)

    
    # Optional: record creation timestamp.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to refresh tokens.
    tokens = relationship("TokenDetails", back_populates="user", cascade="all, delete-orphan")

class AdminUserDetails(Base):
    __tablename__ = "admin_details"
    
    email = Column(String(100), primary_key=True, unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)  # Hashed password storage.
    role = Column(String(10), default="user", nullable=False)  # Default role is 'user'.


class TokenDetails(Base):
    __tablename__ = "token_details"
    
    # Unique token identifier.
    id = Column(String, primary_key=True, unique=True, default=lambda: str(uuid.uuid4()))
    # Links token to the user by phone number.
    user_id = Column(String(10), ForeignKey("user_details.phone_number", ondelete="CASCADE"), nullable=False)
    refresh_token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship back to the user.
    user = relationship("UserDetails", back_populates="tokens")

class Option(Base):
    __tablename__ = "researcher"

    id        = Column(Integer, primary_key=True, index=True)
    title     = Column(String, nullable=False)
    author    = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    message   = Column(Text, nullable=False)
    service   = Column(ARRAY(String), nullable=False)

class PushToken(Base):
    __tablename__ = "push_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(10), ForeignKey("user_details.phone_number", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class PanVerification(Base):
    __tablename__ = "pan_verifications"

    PANnumber = Column(String, primary_key=True, index=True)
    APICount = Column(Integer, default=0)

class KYCUser(Base):
    __tablename__ = "kyc_users_details"
    id = Column(Integer, primary_key=True, index=True)
    # This column is used to store the OTP verification generated UUID.
    UUID_id = Column(String, unique=True, index=True, nullable=False)
    mobile = Column(String, nullable=False)
    email = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    father_name = Column(String, nullable=True)
    alternate_mobile = Column(String, nullable=True)
    dob = Column(Date, nullable=True)
    age = Column(Integer, nullable=True)
    nationality = Column(String, nullable=True)
    pan_no = Column(String, nullable=True)
    aadhaar_no = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    marital_status = Column(String, nullable=True)
    state = Column(String, nullable=True)
    city = Column(String, nullable=True)
    address = Column(String, nullable=True)
    pin_code = Column(String, nullable=True)
    occupation = Column(String, nullable=True)
    user_image = Column(String, nullable=True)
    # The second extra column
    esign_pdf = Column(String, nullable=True)
    group_id = Column(String, unique=True, index=True, nullable=True)
    director_name = Column(String, nullable=True)
    gst_no = Column(String, nullable=True)
    gst_pdf = Column(String, nullable=True)
    # The third extra column for steps
    step_first = Column(Boolean, nullable=False, default=False)
    step_second = Column(Boolean, nullable=False, default=False)
    step_third = Column(Boolean, nullable=False, default=False)
    step_four = Column(Boolean, nullable=False, default=False)
    signature_url = Column(String, nullable=True)
    complete_signature_url = Column(String, nullable=True)
    faild_error = Column(String, nullable=True)




class EStamp(Base):
    __tablename__ = "estamp"

    id = Column(Integer, primary_key=True, index=True)
    UUID_id = Column(String, unique=True, index=True, nullable=False)
    first_party_name = Column(String(100), nullable=False)
    second_party_name = Column(String(100), nullable=False)
    stamp_duty_paid_by = Column(String(100), nullable=False)
    stamp_duty_value = Column(String(100), nullable=False)
    purpose_of_stamp_duty = Column(String(255), nullable=True)
    article_id = Column(String(100), nullable=False)
    consideration_price = Column(String(100), nullable=False)
    branch_id = Column(String(100), nullable=False)
    procure = Column(Boolean, default=False)
    recepient_email = Column(String(100), nullable=True)
    mail_subject = Column(String(255), nullable=False)
    mail_body = Column(String, nullable=False)
    city = Column(String, nullable=False)
    pan = Column(String, nullable=False)
    mobile = Column(String(20), nullable=False)
    # Here we store the file information as a string (e.g., file path or base64 encoded text).
    file = Column(String, nullable=True)


class Lead(Base):
    __tablename__ = "crm_lead"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    full_name         = Column(String(100), nullable=True)
    father_name       = Column(String(100), nullable=True)
    email             = Column(String(100), nullable=True, index=True)
    mobile            = Column(String(20), nullable=True, index=True)
    alternate_mobile  = Column(String(20), nullable=True)
    aadhaar           = Column(String(12), nullable=True)
    pan               = Column(String(10), nullable=True)
    gstin             = Column(String(15), nullable=True)

    state             = Column(String(100), nullable=True)
    city              = Column(String(100), nullable=True)
    district          = Column(String(100), nullable=True)
    address           = Column(Text, nullable=True)

    dob               = Column(Date, nullable=True)
    occupation        = Column(String(100), nullable=True)
    segment           = Column(Text, nullable=True)  # Store as JSON string
    experience        = Column(String(50), nullable=True)
    investment        = Column(String(50), nullable=True)

    lead_response_id  = Column(Integer, ForeignKey("crm_lead_response.id"), nullable=True)
    lead_source_id    = Column(Integer, ForeignKey("crm_lead_source.id"), nullable=True)

    created_by        = Column(String(100), nullable=True)
    created_by_name   = Column(String(100), nullable=True)
    comment           = Column(Text, nullable=True)  # Store as JSON string

    aadhar_front_pic  = Column(String(255), nullable=True)
    aadhar_back_pic   = Column(String(255), nullable=True)
    pan_pic           = Column(String(255), nullable=True)
    kyc               = Column(Boolean, default=False, nullable=True)
    kyc_id            = Column(Integer, nullable=True)

    is_old_lead       = Column(Boolean, default=False, nullable=True)
    call_back_date    = Column(DateTime, nullable=True)
    lead_status       = Column(String(50), nullable=True)

    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    branch_id         = Column(Integer, ForeignKey("crm_branch_details.id"), nullable=True)

    branch            = relationship("BranchDetails", back_populates="leads")
    payments      = relationship("Payment", back_populates="lead")
    stories           = relationship("LeadStory", back_populates="lead", cascade="all, delete-orphan")
    lead_source       = relationship("LeadSource", back_populates="leads")
    lead_response     = relationship("LeadResponse", back_populates="leads")
    assignment = relationship("LeadAssignment", back_populates="lead", uselist=False)
 

class Payment(Base):
    __tablename__ = "crm_payment"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(100), nullable=False)
    email            = Column(String(100), nullable=False)
    phone_number     = Column(Text, nullable=False)
    # ← make this a String so it can hold "order_xxx"
    order_id         = Column(String(100), nullable=True, index=True)

    Service          = Column(String(50), nullable=True)
    paid_amount      = Column(Float, nullable=False)
    status           = Column(String(50), nullable=True)
    mode             = Column(String(50), nullable=False)
    is_send_invoice  = Column(Boolean, nullable=False, default=False)
    description      = Column(Text, nullable=True)
    transaction_id   = Column(String(100), nullable=True)
    user_id          = Column(Integer, nullable=True)
    branch_id        = Column(Integer, nullable=True)

    created_at       = Column(
                         DateTime(timezone=True),
                         server_default=func.now(),
                         nullable=False
                      )

    # foreign key to Lead, many payments per lead
    lead_id          = Column(Integer, ForeignKey("crm_lead.id"), nullable=True)
    lead             = relationship("Lead", back_populates="payments")



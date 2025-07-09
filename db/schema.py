from pydantic import BaseModel, Field, validator, EmailStr
from typing import List, Optional, Literal, Union
from datetime import datetime, date
from pydantic import ConfigDict

from random import randint


class UserOut(BaseModel):
    name: str
    phone_number: str
    role: str
    service: Union[str, List[str]]
    email: EmailStr
    created_at: datetime
    service_active_date: str

    class Config:
        orm_mode = True
    
# Schema for OTP request (for phone login).
class OTPRequest(BaseModel):
    phone_number: str = Field(..., pattern=r"^\d{10}$", example="9876543210")


# Schema for OTP verification.
class OTPVerify(BaseModel):
    phone_number: str = Field(..., pattern=r"^\d{10}$", example="9876543210")
    otp: str = Field(..., min_length=4, max_length=6, example="123456")

# Schema for user registration with phone, email, and password.
class UserSignupSchema(BaseModel):
    name: str = Field(..., example="John")
    service: Union[str, List[str]] = Field(..., example=["cash", "equity"])
    country_code: str = Field(
        ..., 
        pattern=r"^\+\d{1,4}$", 
        description="Country code starting with '+', e.g., +1 or +91",
        example="+91"
    )
    phone_number: str = Field(
        ..., 
        pattern=r"^\d{10}$", 
        description="10-digit phone number",
        example="9876543210"
    )
    email: EmailStr
    password: str = Field(..., min_length=6, example="secret123")

    @validator("phone_number")
    def phone_must_be_ten_digits(cls, v):
        if len(v) != 10:
            raise ValueError("Phone number must be exactly 10 digits")
        return v

# Schema for requesting a new access token via refresh token.
class RefreshTokenRequest(BaseModel):
    token: str

class PasswordReset(BaseModel):
    phone_number: str = Field(..., pattern=r"^\d{10}$")
    otp: str
    new_password: str

class UserEditSchema(BaseModel):
    email: Optional[EmailStr] = None
    service: Optional[Union[str, List[str]]] = None
    service_active_date: str = None

    class Config:
        orm_mode = True

class PushNotification(BaseModel):
    msg_title: str = None
    msg_body: str = None
    service: Union[str, List[str]] = None

    class Config:
        orm_mode = True

class OptionBase(BaseModel):
    title: str
    author: str
    message: str
    service: List[str]

class OptionCreate(OptionBase):
    pass

class OptionUpdate(BaseModel):
    title: Optional[str]          = None
    author: Optional[str]         = None
    message: Optional[str]        = None
    service: Optional[Union[str, List[str]]] = None

class OptionOut(OptionBase):
    id: int
    timestamp: datetime

    # ← Pydantic v2 way to enable from_orm
    model_config = ConfigDict(from_attributes=True)


# CategoryType = Literal["Nifty 50", "Sensex", "Bank Nifty"]
ActionType = Literal["Buy", "Sell", "Hold"]
TradeType = Literal["Intraday", "Positional", "Swing", "Momentum"]
OptionType = Literal["Call", "Put"]


class KYCOTPRequest(BaseModel):
    mobile: str
    email: EmailStr

class KYCOTPVerifyRequest(BaseModel):
    mobile: str
    email: EmailStr
    otp: str

class KYCDetails(BaseModel):
    UUID_id: str  
    mobile: str
    email: EmailStr
    full_name: Optional[str] = None
    father_name: Optional[str] = None
    alternate_mobile: Optional[str] = None
    dob: Optional[date] = None
    age: Optional[int] = None
    nationality: Optional[str] = None
    pan_no: Optional[str] = None
    aadhaar_no: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    pin_code: Optional[str] = None
    occupation: Optional[str] = None
    user_image: Optional[str] = None
    esign_pdf: Optional[str] = None
    group_id: Optional[str] = None
    director_name: Optional[str] = None
    gst_no: Optional[str] = None
    gst_pdf: Optional[str] = None
    step_first: Optional[bool] = None
    step_second: Optional[bool] = None
    step_third: Optional[bool] = None
    step_four: Optional[bool] = None
    signature_url: Optional[str] = None
    complete_signature_url: Optional[str] = None
    faild_error: Optional[str] = None

    class Config:
        orm_mode = True

class OTP(BaseModel):
    id: int
    mobile: str
    otp: int
    timestamp: datetime

    class Config:
        orm_mode = True

class CustomerDetails(BaseModel):
    customer_id:    int
    customer_email: str
    customer_phone: str

    # replace orm_mode = True
    model_config = ConfigDict(from_attributes=True)


class CreateOrderRequest(BaseModel):
    order_amount:      float
    order_currency:    str                   = Field("INR", min_length=3, max_length=3)
    customer_details:  CustomerDetails
    order_note:        str | None            = None
    payment_type:      str | None            = None
    payment_status:    str | None            = None
    timestamp:         datetime              = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)
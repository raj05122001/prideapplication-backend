from pydantic import BaseModel, Field, validator, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, date

from random import randint


class UserOut(BaseModel):
    name: str
    phone_number: str
    role: str
    service: str
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
    service: str = Field(..., example="cash")
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

class OptionBase(BaseModel):
    title: str = Field(..., example="Rapid Stock Option (…)") 
    author: str = Field(..., example="Pradeep")
    timestamp: datetime = Field(..., example="2025-06-11T10:27:40Z")
    message: str = Field(..., example="OPTION:CALL BUY AARTIND 490 …")
    service: str = Field(..., example="cash")

class OptionCreate(OptionBase):
    pass

class OptionUpdate(BaseModel):
    title: Optional[str]
    author: Optional[str]
    timestamp: Optional[datetime]
    message: Optional[str]
    service: str = Field(..., example="cash")

class OptionOut(OptionBase):
    id: int

    class Config:
        orm_mode = True

class PasswordReset(BaseModel):
    phone_number: str = Field(..., pattern=r"^\d{10}$")
    otp: str
    new_password: str
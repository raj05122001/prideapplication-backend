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
    service = Column(String(100), nullable=False)
    service_active_date = Column(String(100), nullable=True, default=None)

    
    # Optional: record creation timestamp.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to refresh tokens.
    tokens = relationship("TokenDetails", back_populates="user", cascade="all, delete-orphan")

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

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    message = Column(Text, nullable=False)
    service = Column(String, nullable=False)


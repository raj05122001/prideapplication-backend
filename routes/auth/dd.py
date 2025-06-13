from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from config import logger
from db.schema import UserOut 
# Import your DB session, models, and schemas
from db.connection import get_db
from db.models import UserDetails # Ensure UserDetails now has a 'password' field.
from db.schema import OTPRequest, OTPVerify, UserSignupSchema, RefreshTokenRequest  # Adjust as needed.
from routes.auth.otp_service import send_otp, verify_otp, validate_phone
from routes.auth.JWTSecurity import create_access_token, create_refresh_token, save_refresh_token, verify_token
from fastapi.responses import JSONResponse


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Temporary in-memory store for pending registration details.
pending_registrations = {}

@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def initiate_registration(user_data: UserSignupSchema,background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Initiates registration by validating details, storing them temporarily, and sending an OTP.
    The user is not yet added to the database until OTP is verified.
    """
    # Check if user with given email or phone already exists
    existing_user_email = db.query(UserDetails).filter(UserDetails.email == user_data.email).first()
    existing_user_phone = db.query(UserDetails).filter(UserDetails.phone_number == user_data.phone_number).first()
    if existing_user_email or existing_user_phone:
        raise HTTPException(status_code=400, detail="User with given email or phone already exists")
    # phone_number = user_data.phone_number
    # validate_phone(phone_number)
    # Store registration details temporarilys
    pending_registrations[user_data.phone_number] = user_data.dict()
    try:
        send_otp(user_data.phone_number, background_tasks, db)
        logger.info(f"OTP sent for registration to phone {user_data.phone_number}")
        return {"message": "OTP sent for registration. Please verify to complete registration."}
    except Exception as e:
        logger.error(f"Error sending OTP to {user_data.phone_number}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error sending OTP. Please try again later.")


@router.post("/login", summary="Email/Password Login")
def login_email(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticates the user by email and password.
    The OAuth2PasswordRequestForm's 'username' field will be treated as email.
    """
    user = db.query(UserDetails).filter(UserDetails.email == form_data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Generate tokens
    access_token = create_access_token({"sub": user.email, "role": user.role, "phone_number": user.phone_number, "name": user.name, "service": user.service})
    refresh_token = create_refresh_token(user.phone_number)  # using phone as unique id for refresh tokens
    save_refresh_token(db, user.phone_number, refresh_token)
    
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/send-otp", summary="Send OTP for Phone Login")
def send_otp_endpoint(data: OTPRequest,background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Sends an OTP to the given phone number.
    """
    phone_number = data.phone_number
    email = data.email
    validate_phone(phone_number)
    
    # Ensure the user exists (registration is required)
    user = db.query(UserDetails).filter(UserDetails.phone_number == phone_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Phone number not registered. Please register first.")
    
    otp_response = send_otp_msg_mail(phone_number,background_tasks, db, email)
    return otp_response


@router.post("/verify-otp", summary="Verify OTP for Registration or Login")
def verify_otp_endpoint(data: OTPVerify, db: Session = Depends(get_db)):
    """
    Verifies OTP. If registration details are pending for the phone number, completes registration.
    Otherwise, treats the request as an OTP login.
    """
    phone_number = data.phone_number
    validate_phone(phone_number)
    
    otp_result = verify_otp(phone_number, data.otp,db)
    if otp_result.get("status") != "success":
        logger.error(f"OTP verification failed for phone {phone_number}")
        raise HTTPException(status_code=400, detail="OTP verification failed")
    
    # Check if this is for registration
    if phone_number in pending_registrations:
        reg_data = pending_registrations.pop(phone_number)
        hashed_password = pwd_context.hash(reg_data["password"])
        new_user = UserDetails(
            phone_number=reg_data["phone_number"],
            email=reg_data["email"],
            name=reg_data["name"],
            service=reg_data["service"],
            password=hashed_password,
            role="user"  # default role for regular users
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"User registered successfully for phone {phone_number}")
        return {
            "status": "success",
            "status_code": 200,
            "phone_number": phone_number,
            "registration": True,
            "message": "Registration completed successfully."
        }
    else:
        # If no pending registration, assume OTP login for existing user.
        user = db.query(UserDetails).filter(UserDetails.phone_number == phone_number).first()
        if not user:
            logger.error(f"OTP verified for phone {phone_number} but user not found.")
            raise HTTPException(status_code=404, detail="User not registered")
        access_token = create_access_token({"sub": user.phone_number, "role": user.role})
        refresh_token = create_refresh_token(user.phone_number)
        save_refresh_token(db, user.phone_number, refresh_token)
        logger.info(f"User login via OTP successful for phone {phone_number}")
        return {
            "message": "OTP verified successfully.",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "status": "success",
            "status_code": 200,
            "phone_number": phone_number,
            "registration": True
        }


@router.post("/refresh", summary="Refresh Access Token")
def refresh_access_token(data: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Refreshes the access token using a valid refresh token.
    """
    payload = verify_token(data.token)
    if not payload or payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # Retrieve the user identifier from token (we use phone_number for refresh tokens)
    user_identifier = payload.get("sub")
    user = db.query(UserDetails).filter(UserDetails.phone_number == user_identifier).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Generate new access token
    new_access_token = create_access_token({"sub": user.phone_number, "role": user.role})
    return {"access_token": new_access_token, "token_type": "bearer"}

@router.get("/users", summary="Get all users", response_model=list[UserOut])
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(UserDetails).all()
    return users

@router.get("/users/find", summary="Find user by phone or email", response_model=UserOut)
def find_user(phone: str = None, email: str = None, db: Session = Depends(get_db)):
    if phone:
        user = db.query(UserDetails).filter(UserDetails.phone_number == phone).first()
    elif email:
        user = db.query(UserDetails).filter(UserDetails.email == email).first()
    else:
        raise HTTPException(status_code=400, detail="Phone or Email must be provided")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/users/{phone_number}", summary="Delete a user by phone number")
def delete_user(phone_number: str, db: Session = Depends(get_db)):
    user = db.query(UserDetails).filter(UserDetails.phone_number == phone_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    return JSONResponse(content={"message": "User deleted successfully"}, status_code=200)

from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from config import logger
from db.connection import get_db
from db.models import AdminUserDetails 
from db.schema import  AdminUserSignupSchema
from routes.auth.JWTSecurity import create_access_token, create_refresh_token, save_refresh_token, verify_token
from fastapi.security import OAuth2PasswordBearer

# add at top, after your other imports
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

router = APIRouter(
    prefix="/web/auth",
    tags=["web login"],
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Temporary in-memory store for pending registration details.

@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def initiate_registration(user_data: AdminUserSignupSchema, db: Session = Depends(get_db)):
    """
    Initiates registration by validating details, storing them temporarily, and sending an OTP.
    The user is not yet added to the database until OTP is verified.
    """
    # Check if user with given email or phone already exists
    existing_user_email = db.query(AdminUserDetails).filter(AdminUserDetails.email == user_data.email).first()
    if existing_user_email :
        raise HTTPException(status_code=400, detail="User with given email or phone already exists")
    
    else:
        hashed_password = pwd_context.hash(user_data.password)
        email=user_data.email
        new_user = AdminUserDetails(
            email=user_data.email,
            name=user_data.name,
            password=hashed_password,
            role=user_data.role,  
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"User registered successfully for email {email}")
        return {
            "status": "success",
            "status_code": 200,
            "email": email,
            "registration": True,
            "message": "Registration completed successfully."
        }


@router.post("/login", summary="Email/Password Login")
def login_email(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticates the user by email and password.
    The OAuth2PasswordRequestForm's 'username' field will be treated as email.
    """
    user = db.query(AdminUserDetails).filter(AdminUserDetails.email == form_data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Generate tokens
    access_token = create_access_token({"sub": user.email, "role": user.role, "name": user.name})
    refresh_token = create_refresh_token(user.email)  # using phone as unique id for refresh tokens
    save_refresh_token(db, user.email, refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }



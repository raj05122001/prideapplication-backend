from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = 5432
DB_NAME = os.getenv("DB_NAME")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")

pw_quoted = quote_plus(DB_PASSWORD)

DATABASE_URL = (
    f"postgresql://"
    f"{DB_USERNAME}:{pw_quoted}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

print(DATABASE_URL)

engine = create_engine(DATABASE_URL, echo=True)

# Create a session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

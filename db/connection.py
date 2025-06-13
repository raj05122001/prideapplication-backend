from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database configuration
DB_USERNAME = "pridenotification"
DB_PASSWORD = "0000"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "prideappdb"

# psql -U pridenotification -d prideappdb -h localhost -p 5432
# DROP TABLE user_details;   delete table


# SQLAlchemy database URL
DATABASE_URL = f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
# DATABASE_URL = f"postgresql+psycopg2://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create engine
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

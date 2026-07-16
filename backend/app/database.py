import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ------------------------
# Configuration
# ------------------------

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./librarytools.db",
)


# ------------------------
# Database Engine
# ------------------------

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)


# ------------------------
# Base Model
# ------------------------

class Base(DeclarativeBase):
    pass
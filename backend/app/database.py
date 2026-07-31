import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ------------------------
# Configuration
# ------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BACKEND_DIR / 'librarytools.db'}",
)

if DATABASE_URL.startswith("sqlite:///./"):
    database_path = DATABASE_URL.removeprefix("sqlite:///./")
    DATABASE_URL = f"sqlite:///{BACKEND_DIR / database_path}"

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False


# ------------------------
# Database Engine
# ------------------------

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# ------------------------
# Base Model
# ------------------------

class Base(DeclarativeBase):
    pass


def migrate_existing_database() -> None:
    """Add Lendery availability columns without replacing local SQLite data."""
    inspector = inspect(engine)
    if "lendery_items" not in inspector.get_table_names():
        return

    existing = {
        column["name"]
        for column in inspector.get_columns("lendery_items")
    }
    columns = {
        "library_url": "VARCHAR(500)",
        "availability_status": (
            "VARCHAR(20) NOT NULL DEFAULT 'unknown'"
        ),
        "available_copies": "INTEGER",
        "total_copies_at_branch": "INTEGER",
        "availability_checked_at": "DATETIME",
        "availability_error": "TEXT",
    }
    with engine.begin() as connection:
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(
                    text(
                        f"ALTER TABLE lendery_items "
                        f"ADD COLUMN {name} {definition}"
                    )
                )

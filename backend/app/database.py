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

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+psycopg://",
        1,
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
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
    pool_pre_ping=True,
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


def _replace_legacy_sqlite_unique_constraints() -> None:
    """Replace pre-multiclub global unique constraints with scoped ones."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    definitions = {
        "bookclub_members": (
            "email",
            """CREATE TABLE bookclub_members_new (
                id INTEGER PRIMARY KEY,
                club_id INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                email VARCHAR(320) NOT NULL,
                joined_on DATE NOT NULL,
                active BOOLEAN NOT NULL DEFAULT 1,
                notes TEXT,
                CONSTRAINT uq_bookclub_club_email UNIQUE (club_id, email),
                FOREIGN KEY(club_id) REFERENCES book_clubs(id) ON DELETE CASCADE
            )""",
            "id, club_id, name, email, joined_on, active, notes",
            (
                "CREATE INDEX idx_bookclub_members_club_id ON bookclub_members(club_id)",
                "CREATE INDEX ix_bookclub_members_email ON bookclub_members(email)",
            ),
        ),
        "bookclub_books": (
            "isbn",
            """CREATE TABLE bookclub_books_new (
                id INTEGER PRIMARY KEY,
                club_id INTEGER NOT NULL,
                title VARCHAR(300) NOT NULL,
                author VARCHAR(200) NOT NULL,
                cover_image_url VARCHAR(500),
                description TEXT,
                publication_date DATE,
                isbn VARCHAR(20),
                publisher VARCHAR(200),
                page_count INTEGER,
                genres VARCHAR(500),
                series VARCHAR(300),
                catalogue_url VARCHAR(500),
                discussion_notes TEXT,
                CONSTRAINT uq_bookclub_club_isbn UNIQUE (club_id, isbn),
                FOREIGN KEY(club_id) REFERENCES book_clubs(id) ON DELETE CASCADE
            )""",
            "id, club_id, title, author, cover_image_url, description, publication_date, isbn, publisher, page_count, genres, series, catalogue_url, discussion_notes",
            (
                "CREATE INDEX idx_bookclub_books_club_id ON bookclub_books(club_id)",
                "CREATE INDEX ix_bookclub_books_title ON bookclub_books(title)",
                "CREATE INDEX ix_bookclub_books_author ON bookclub_books(author)",
                "CREATE INDEX ix_bookclub_books_isbn ON bookclub_books(isbn)",
            ),
        ),
        "bookclub_templates": (
            "key",
            """CREATE TABLE bookclub_templates_new (
                id INTEGER PRIMARY KEY,
                club_id INTEGER NOT NULL,
                key VARCHAR(80) NOT NULL,
                name VARCHAR(150) NOT NULL,
                kind VARCHAR(20) NOT NULL,
                subject VARCHAR(300),
                body TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                CONSTRAINT uq_bookclub_club_template_key UNIQUE (club_id, key),
                FOREIGN KEY(club_id) REFERENCES book_clubs(id) ON DELETE CASCADE
            )""",
            "id, club_id, key, name, kind, subject, body, updated_at",
            (
                "CREATE INDEX idx_bookclub_templates_club_id ON bookclub_templates(club_id)",
                "CREATE INDEX ix_bookclub_templates_key ON bookclub_templates(key)",
            ),
        ),
    }
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.commit()
        for table_name, (legacy_column, create_sql, columns, indexes) in definitions.items():
            if table_name not in set(inspector.get_table_names()):
                continue
            uniques = inspector.get_unique_constraints(table_name)
            existing_indexes = inspector.get_indexes(table_name)
            has_legacy = any(
                constraint.get("column_names") == [legacy_column]
                for constraint in uniques
            ) or any(
                index.get("unique")
                and index.get("column_names") == [legacy_column]
                for index in existing_indexes
            )
            if not has_legacy:
                continue
            with connection.begin():
                connection.execute(text(f"DROP TABLE IF EXISTS {table_name}_new"))
                connection.execute(text(create_sql))
                connection.execute(
                    text(
                        f"INSERT INTO {table_name}_new ({columns}) "
                        f"SELECT {columns} FROM {table_name}"
                    )
                )
                connection.execute(text(f"DROP TABLE {table_name}"))
                connection.execute(
                    text(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")
                )
                for index_sql in indexes:
                    connection.execute(text(index_sql))
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.commit()


def migrate_existing_database() -> None:
    """Apply small additive migrations without replacing existing data."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "lendery_items" in tables:
        existing = {
            column["name"]
            for column in inspector.get_columns("lendery_items")
        }
        columns = {
            "library_url": "VARCHAR(500)",
            "availability_status": (
                "VARCHAR(20) NOT NULL DEFAULT 'unknown'"
            ),
            "availability_status_version": "INTEGER NOT NULL DEFAULT 1",
            "available_copies": "INTEGER",
            "total_copies_at_branch": "INTEGER",
            "availability_checked_at": "TIMESTAMP",
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

    if "libtools_users" in tables:
        user_columns = {
            column["name"] for column in inspector.get_columns("libtools_users")
        }
        if "session_version" not in user_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE libtools_users ADD COLUMN "
                        "session_version INTEGER NOT NULL DEFAULT 1"
                    )
                )

    if not {"bookclub_books", "bookclub_meetings"}.issubset(tables):
        return

    with engine.begin() as connection:
        if "book_clubs" not in tables:
            connection.execute(
                text(
                    "CREATE TABLE book_clubs ("
                    "id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                    "slug VARCHAR(120) NOT NULL UNIQUE, description TEXT, "
                    "public BOOLEAN NOT NULL DEFAULT 1, "
                    "organizer_name VARCHAR(200), organizer_branch VARCHAR(200))"
                )
            )
        default_club_id = connection.execute(
            text("SELECT id FROM book_clubs ORDER BY id LIMIT 1")
        ).scalar()
        if default_club_id is None:
            connection.execute(
                text(
                    "INSERT INTO book_clubs "
                    "(name, slug, description, public, organizer_name, organizer_branch) "
                    "VALUES ('Science Fiction Book Club', 'science-fiction-book-club', "
                    "'Monthly science fiction reading and discussion.', 1, 'Josh', 'PBRL')"
                )
            )
            default_club_id = connection.execute(
                text("SELECT id FROM book_clubs ORDER BY id LIMIT 1")
            ).scalar_one()

    inspector = inspect(engine)
    scoped_tables = (
        "bookclub_members",
        "bookclub_books",
        "bookclub_meetings",
        "bookclub_templates",
    )
    with engine.begin() as connection:
        for table_name in scoped_tables:
            if table_name not in set(inspector.get_table_names()):
                continue
            columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            if "club_id" not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN club_id INTEGER")
                )
            connection.execute(
                text(
                    f"UPDATE {table_name} SET club_id = :club_id "
                    "WHERE club_id IS NULL"
                ),
                {"club_id": default_club_id},
            )
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_club_id "
                    f"ON {table_name}(club_id)"
                )
            )

    _replace_legacy_sqlite_unique_constraints()

    meeting_columns = {
        column["name"]
        for column in inspector.get_columns("bookclub_meetings")
    }
    with engine.begin() as connection:
        if "book_id" not in meeting_columns:
            connection.execute(
                text(
                    "ALTER TABLE bookclub_meetings "
                    "ADD COLUMN book_id INTEGER"
                )
            )

        meetings = connection.execute(
            text(
                "SELECT id, book_title, book_author, book_id, club_id "
                "FROM bookclub_meetings"
            )
        ).mappings()
        for meeting in meetings:
            if meeting["book_id"] is not None:
                continue
            book_id = connection.execute(
                text(
                    "SELECT id FROM bookclub_books "
                    "WHERE title = :title AND author = :author "
                    "AND club_id = :club_id "
                    "ORDER BY id LIMIT 1"
                ),
                {
                    "title": meeting["book_title"],
                    "author": meeting["book_author"],
                    "club_id": meeting["club_id"] or default_club_id,
                },
            ).scalar()
            if book_id is None:
                connection.execute(
                    text(
                        "INSERT INTO bookclub_books (title, author, club_id) "
                        "VALUES (:title, :author, :club_id)"
                    ),
                    {
                        "title": meeting["book_title"],
                        "author": meeting["book_author"],
                        "club_id": meeting["club_id"] or default_club_id,
                    },
                )
                book_id = connection.execute(
                    text(
                        "SELECT id FROM bookclub_books "
                        "WHERE title = :title AND author = :author "
                        "AND club_id = :club_id "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {
                        "title": meeting["book_title"],
                        "author": meeting["book_author"],
                        "club_id": meeting["club_id"] or default_club_id,
                    },
                ).scalar_one()
            connection.execute(
                text(
                    "UPDATE bookclub_meetings SET book_id = :book_id "
                    "WHERE id = :meeting_id"
                ),
                {"book_id": book_id, "meeting_id": meeting["id"]},
            )

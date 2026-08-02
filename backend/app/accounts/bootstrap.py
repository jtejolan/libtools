import os

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from accounts.auth import set_tools
from accounts.models import LibtoolsUser, ToolAccess
from bookclub.models import BookClub, BookClubAccess
from database import engine
from security import hash_password


def initialize_platform_accounts(db: Session) -> None:
    user = db.scalar(select(LibtoolsUser).order_by(LibtoolsUser.id))
    if user is None:
        legacy_hash = None
        if "lendery_users" in inspect(engine).get_table_names():
            with engine.connect() as connection:
                legacy_hash = connection.execute(
                    text(
                        "SELECT password_hash FROM lendery_users "
                        "WHERE username = 'admin' LIMIT 1"
                    )
                ).scalar()
        password = os.getenv("LIBTOOLS_ADMIN_PASSWORD")
        if legacy_hash is None and (password is None or len(password) < 10):
            raise RuntimeError(
                "Set LIBTOOLS_ADMIN_PASSWORD to at least 10 characters "
                "before starting Libtools for the first time."
            )
        user = LibtoolsUser(
            username=os.getenv("LIBTOOLS_ADMIN_NAME", "admin"),
            password_hash=legacy_hash or hash_password(password or ""),
            role="admin",
        )
        db.add(user)
        db.flush()
        set_tools(
            db,
            user,
            ["bookclub", "storytime", "lendery_manage"],
        )

    elif user.role == "admin":
        existing_tools = set(
            db.scalars(
                select(ToolAccess.tool_key).where(ToolAccess.user_id == user.id)
            )
        )
        if "lendery_manage" not in existing_tools:
            db.add(ToolAccess(user_id=user.id, tool_key="lendery_manage"))

    club = db.scalar(select(BookClub).order_by(BookClub.id))
    if club is None:
        club = BookClub(
            name="Science Fiction Book Club",
            slug="science-fiction-book-club",
            description="Monthly science fiction reading and discussion.",
            organizer_name="Josh",
            organizer_branch="PBRL",
        )
        db.add(club)
        db.flush()

    access = db.scalar(
        select(BookClubAccess).where(
            BookClubAccess.club_id == club.id,
            BookClubAccess.user_id == user.id,
        )
    )
    if access is None:
        db.add(BookClubAccess(club_id=club.id, user_id=user.id, role="owner"))
    db.commit()


def remove_legacy_lendery_accounts() -> None:
    if "lendery_users" not in inspect(engine).get_table_names():
        return
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE lendery_users"))

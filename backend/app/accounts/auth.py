import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts.models import LibtoolsUser, ToolAccess
from accounts.schemas import UserResponse
from dependencies import DatabaseSession
from security import hash_password, verify_password


def normalize_username(value: str) -> str:
    return " ".join(value.split()).casefold()


def generate_recovery_code() -> str:
    return "-".join(
        [secrets.token_hex(4).upper() for _ in range(4)]
    )


def get_user(db: Session, username: str) -> LibtoolsUser | None:
    normalized = normalize_username(username)
    return db.scalar(
        select(LibtoolsUser).where(
            func.lower(LibtoolsUser.username) == normalized
        )
    )


def user_response(db: Session, user: LibtoolsUser) -> UserResponse:
    from bookclub.models import BookClub, BookClubAccess

    tools = list(
        db.scalars(
            select(ToolAccess.tool_key)
            .where(
                ToolAccess.user_id == user.id,
                ToolAccess.tool_key != "lendery_view",
            )
            .order_by(ToolAccess.tool_key)
        )
    )
    clubs = list(
        db.scalars(
            select(BookClub.name)
            .join(BookClubAccess)
            .where(BookClubAccess.user_id == user.id)
            .order_by(BookClub.name)
        )
    )
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        active=user.active,
        must_change_password=user.must_change_password,
        tools=tools,
        clubs=clubs,
        created_at=user.created_at,
    )


def get_current_user(request: Request, db: DatabaseSession) -> LibtoolsUser:
    user_id = request.session.get("libtools_user_id")
    user = db.get(LibtoolsUser, user_id) if isinstance(user_id, int) else None
    session_version = request.session.get("libtools_session_version")
    if (
        user is None
        or not user.active
        or session_version != user.session_version
    ):
        request.session.pop("libtools_user_id", None)
        request.session.pop("libtools_session_version", None)
        request.session.pop("bookclub_id", None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to Libtools",
        )
    return user


CurrentUser = Annotated[LibtoolsUser, Depends(get_current_user)]


def require_platform_admin(user: CurrentUser) -> LibtoolsUser:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Change your temporary password before continuing",
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Libtools administrator access is required",
        )
    return user


def has_tool_access(db: Session, user: LibtoolsUser, tool_key: str) -> bool:
    if user.must_change_password:
        return False
    if user.role == "admin":
        return True
    return db.scalar(
        select(ToolAccess.id).where(
            ToolAccess.user_id == user.id,
            ToolAccess.tool_key == tool_key,
        )
    ) is not None


def require_lendery_view(user: CurrentUser) -> LibtoolsUser:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Change your temporary password before continuing",
        )
    return user


def require_lendery_manage(user: CurrentUser, db: DatabaseSession) -> LibtoolsUser:
    if not has_tool_access(db, user, "lendery_manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lendery edit access is required",
        )
    return user


def verify_login(db: Session, username: str, password: str) -> LibtoolsUser | None:
    user = get_user(db, username)
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return None
    return user


def set_tools(db: Session, user: LibtoolsUser, tools: list[str]) -> None:
    existing = list(
        db.scalars(select(ToolAccess).where(ToolAccess.user_id == user.id))
    )
    for entry in existing:
        db.delete(entry)
    selected = set(tools)
    selected.discard("lendery_view")
    db.add_all(ToolAccess(user=user, tool_key=key) for key in sorted(selected))


def issue_recovery_code(user: LibtoolsUser) -> str:
    code = generate_recovery_code()
    user.recovery_code_hash = hash_password(code)
    return code

import base64
import hashlib
import hmac
import os
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from dependencies import DatabaseSession
from lendery.models import User

Role = Literal["admin", "clerk"]
FIXED_USERS: dict[str, Role] = {
    "admin": "admin",
    "clerk": "clerk",
}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserResponse(BaseModel):
    username: str
    role: Role


class PasswordChangeRequest(BaseModel):
    username: Literal["admin", "clerk"]
    new_password: str = Field(min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def password_cannot_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("password cannot be blank")
        return value


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return "scrypt${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_text, expected_text = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def get_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def initialize_fixed_users(db: Session) -> None:
    missing = [
        username
        for username in FIXED_USERS
        if get_user(db, username) is None
    ]
    if not missing:
        return

    passwords = {
        "admin": os.getenv("LENDERY_ADMIN_PASSWORD"),
        "clerk": os.getenv("LENDERY_CLERK_PASSWORD"),
    }
    unset = [
        f"LENDERY_{username.upper()}_PASSWORD"
        for username in missing
        if not passwords[username]
    ]
    if unset:
        names = ", ".join(unset)
        raise RuntimeError(
            f"Set {names} before starting Lendery for the first time."
        )

    for username in missing:
        password = passwords[username]
        if password is None or len(password) < 8:
            raise RuntimeError(
                f"LENDERY_{username.upper()}_PASSWORD must be at least "
                "8 characters."
            )
        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=FIXED_USERS[username],
            )
        )
    db.commit()


def get_current_user(
    request: Request,
    db: DatabaseSession,
) -> User:
    username = request.session.get("lendery_username")
    user = get_user(db, username) if isinstance(username, str) else None
    if user is None or not user.active:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use Lendery",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_authenticated(user: CurrentUser) -> User:
    return user


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return user


router = APIRouter(prefix="/lendery/auth", tags=["lendery-auth"])


@router.post("/login", response_model=UserResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    db: DatabaseSession,
) -> User:
    user = get_user(db, credentials.username.strip().lower())
    if (
        user is None
        or not user.active
        or not verify_password(credentials.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    request.session.clear()
    request.session["lendery_username"] = user.username
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> User:
    return user


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    changes: PasswordChangeRequest,
    db: DatabaseSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> None:
    user = get_user(db, changes.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user.password_hash = hash_password(changes.new_password)
    db.commit()

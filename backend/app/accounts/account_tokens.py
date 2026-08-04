import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts.models import AccountToken, LibtoolsUser

EMAIL_VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"
EMAIL_VERIFICATION_LIFETIME = timedelta(hours=24)
PASSWORD_RESET_LIFETIME = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def issue_token(
    db: Session,
    user: LibtoolsUser,
    purpose: str,
    lifetime: timedelta,
) -> str:
    """Replace outstanding tokens of this kind and return the one raw value."""
    outstanding = db.scalars(
        select(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
        )
    )
    for token in outstanding:
        db.delete(token)

    raw_token = secrets.token_urlsafe(32)
    db.add(
        AccountToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_digest(raw_token),
            expires_at=_now() + lifetime,
        )
    )
    return raw_token


def revoke_tokens(db: Session, user: LibtoolsUser, purpose: str) -> None:
    tokens = db.scalars(
        select(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
        )
    )
    for token in tokens:
        db.delete(token)


def consume_token(
    db: Session,
    raw_token: str,
    purpose: str,
) -> AccountToken | None:
    if not raw_token:
        return None
    token = db.scalar(
        select(AccountToken).where(
            AccountToken.token_hash == _digest(raw_token),
            AccountToken.purpose == purpose,
        )
    )
    if (
        token is None
        or token.used_at is not None
        or _as_utc(token.expires_at) <= _now()
    ):
        return None
    token.used_at = _now()
    return token

"""Hashed/expiring tokens for participant email verification and password
reset. Parallels accounts/account_tokens.py exactly, but for
ParticipantAccount/ParticipantAccountToken instead of LibtoolsUser/
AccountToken — kept separate rather than generalized, since the two account
systems are deliberately not unified.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from bookclub.participant_models import ParticipantAccount, ParticipantAccountToken

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
    participant: ParticipantAccount,
    purpose: str,
    lifetime: timedelta,
) -> str:
    """Replace outstanding tokens of this kind and return the one raw value."""
    outstanding = db.scalars(
        select(ParticipantAccountToken).where(
            ParticipantAccountToken.participant_id == participant.id,
            ParticipantAccountToken.purpose == purpose,
            ParticipantAccountToken.used_at.is_(None),
        )
    )
    for token in outstanding:
        db.delete(token)

    raw_token = secrets.token_urlsafe(32)
    db.add(
        ParticipantAccountToken(
            participant_id=participant.id,
            purpose=purpose,
            token_hash=_digest(raw_token),
            expires_at=_now() + lifetime,
        )
    )
    return raw_token


def revoke_tokens(db: Session, participant: ParticipantAccount, purpose: str) -> None:
    tokens = db.scalars(
        select(ParticipantAccountToken).where(
            ParticipantAccountToken.participant_id == participant.id,
            ParticipantAccountToken.purpose == purpose,
            ParticipantAccountToken.used_at.is_(None),
        )
    )
    for token in tokens:
        db.delete(token)


def consume_token(
    db: Session,
    raw_token: str,
    purpose: str,
) -> ParticipantAccountToken | None:
    if not raw_token:
        return None
    token = db.scalar(
        select(ParticipantAccountToken).where(
            ParticipantAccountToken.token_hash == _digest(raw_token),
            ParticipantAccountToken.purpose == purpose,
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

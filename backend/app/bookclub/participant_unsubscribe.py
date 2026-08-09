"""Signs/verifies participant unsubscribe tokens.

Unlike ParticipantAccountToken (participant_tokens.py), these are not
single-use rows in a table — an unsubscribe link embedded in an email must
keep working no matter how many times it's clicked (idempotent), and must
work without an active login session (the whole point: it's read cold from
an email client). itsdangerous signs the participant id directly, with a
distinct salt so it can't be confused with a session or any other signed
value, reusing the same LIBTOOLS_SESSION_SECRET rather than adding a new
env var.
"""

import os
import secrets

from itsdangerous import BadSignature, URLSafeSerializer

_SALT = "bookclub-participant-unsubscribe"


def _secret() -> str:
    secret = os.getenv("LIBTOOLS_SESSION_SECRET")
    if secret:
        return secret
    if os.getenv("RAILWAY_ENVIRONMENT"):
        raise RuntimeError(
            "LIBTOOLS_SESSION_SECRET must be set when running on Railway — "
            "refusing to start with a randomly generated secret, which "
            "would silently invalidate unsubscribe links across restarts."
        )
    return secrets.token_urlsafe(32)


_serializer = URLSafeSerializer(_secret(), salt=_SALT)


def issue_unsubscribe_token(member_id: int) -> str:
    return _serializer.dumps(member_id)


def verify_unsubscribe_token(token: str) -> int | None:
    try:
        value = _serializer.loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, int) else None

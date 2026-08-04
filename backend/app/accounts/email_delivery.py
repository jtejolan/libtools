"""Email delivery seam for account messages.

Token creation and account flows are complete, but no mail provider is wired in
yet. Replace these functions with the eventual provider implementation; callers
already pass fully-qualified, single-use links.
"""

import logging

logger = logging.getLogger(__name__)

DELIVERY_CONFIGURED = False


def send_verification_email(
    *, recipient: str, username: str, verification_url: str
) -> bool:
    logger.info(
        "Email verification requested for %s; email delivery is not configured",
        recipient,
    )
    return False


def send_password_reset_email(
    *, recipient: str, username: str, reset_url: str
) -> bool:
    logger.info(
        "Password reset requested for %s; email delivery is not configured",
        recipient,
    )
    return False

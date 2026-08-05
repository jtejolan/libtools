"""Bookclub-specific email sends, built on the shared Resend transport.

Bookclub templates are plain `{{placeholder}}` text (see crud.py's
DEFAULT_TEMPLATES), not the branded HTML documents accounts/email_delivery
builds — send_email() derives a minimal HTML body from the plain text when
none is given.
"""

from email_delivery import DELIVERY_CONFIGURED, RESEND_FROM_ADDRESS, send_email

__all__ = ["DELIVERY_CONFIGURED", "send_onboarding_email", "send_reminder_batch"]


def send_onboarding_email(*, recipient: str, subject: str, body: str) -> bool:
    return send_email(to=[recipient], subject=subject, text_body=body)


def send_reminder_batch(*, recipients: list[str], subject: str, body: str) -> bool:
    # Resend requires a non-empty `to`; the real audience goes in `bcc` so
    # recipients don't see each other's addresses in a batch send.
    return send_email(
        to=[RESEND_FROM_ADDRESS] if RESEND_FROM_ADDRESS else [],
        bcc=recipients,
        subject=subject,
        text_body=body,
    )

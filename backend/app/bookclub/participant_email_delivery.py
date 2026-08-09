"""Email sends for participant accounts, built on the shared Resend
transport. Plain-text, like bookclub/email_delivery.py's member sends,
rather than accounts/email_delivery.py's branded HTML documents — these are
one-off transactional links, not a first-impression "welcome" email.
"""

from email_delivery import DELIVERY_CONFIGURED, send_email

__all__ = [
    "DELIVERY_CONFIGURED",
    "send_verification_email",
    "send_password_reset_email",
    "send_password_changed_email",
    "send_broadcast_email",
]


def send_verification_email(
    *, recipient: str, name: str, club_name: str, verification_url: str
) -> bool:
    subject = f"Verify your email for {club_name}"
    text_body = (
        f"Hi {name},\n\n"
        f"You're joining {club_name} on Book Club. Confirm this email "
        "address to finish setting up your account:\n\n"
        f"{verification_url}\n\n"
        "This link expires in 24 hours."
    )
    return send_email(to=[recipient], subject=subject, text_body=text_body)


def send_password_reset_email(
    *, recipient: str, name: str, club_name: str, reset_url: str
) -> bool:
    subject = f"Reset your {club_name} password"
    text_body = (
        f"Hi {name},\n\n"
        f"We received a request to reset your password for {club_name} on "
        f"Book Club:\n\n{reset_url}\n\n"
        "This link expires in 1 hour and can only be used once. If you "
        "didn't request this, you can safely ignore this email."
    )
    return send_email(to=[recipient], subject=subject, text_body=text_body)


def send_password_changed_email(*, recipient: str, name: str, club_name: str) -> bool:
    subject = f"Your {club_name} password was changed"
    text_body = (
        f"Hi {name},\n\n"
        f"The password on your {club_name} account was just changed. If "
        "this wasn't you, use the password reset link on your club's page "
        "to secure your account."
    )
    return send_email(to=[recipient], subject=subject, text_body=text_body)


def send_broadcast_email(*, recipient: str, subject: str, body: str, unsubscribe_url: str) -> bool:
    """A facilitator-authored broadcast. Sent one-at-a-time (not BCC'd like
    bookclub/email_delivery.send_reminder_batch's member reminders) so each
    recipient gets their own working, no-login-required unsubscribe link —
    see participant_unsubscribe.py.
    """
    text_body = f"{body}\n\n---\nDon't want these emails? Unsubscribe: {unsubscribe_url}"
    return send_email(to=[recipient], subject=subject, text_body=text_body)

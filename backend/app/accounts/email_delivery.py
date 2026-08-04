"""Email delivery for account messages, sent via Resend (https://resend.com).

Configured through RESEND_API_KEY and RESEND_FROM_ADDRESS env vars. When
either is unset, DELIVERY_CONFIGURED is False and sends are skipped — callers
already handle that by falling back to recovery codes.
"""

import html
import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_ADDRESS = os.getenv("RESEND_FROM_ADDRESS")

DELIVERY_CONFIGURED = bool(RESEND_API_KEY and RESEND_FROM_ADDRESS)


def _send(*, recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    if not DELIVERY_CONFIGURED:
        logger.info(
            "Email delivery is not configured; skipping send to %s", recipient
        )
        return False
    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_FROM_ADDRESS,
                "to": [recipient],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send email to %s via Resend", recipient)
        return False


def _wrapper(body_html: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;color:#183b33;">
  <p style="margin:0 0 24px;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#e85e16;">Library Tools</p>
  {body_html}
  <p style="margin:32px 0 0;font-size:12px;color:#746f62;">If you didn't request this, you can safely ignore this email.</p>
</div>"""


def _button(url: str, label: str) -> str:
    return (
        f'<a href="{html.escape(url)}" '
        'style="display:inline-block;margin:20px 0;padding:12px 20px;'
        'border-radius:6px;background:#163e34;color:#fffaf0;'
        'font-weight:600;text-decoration:none;">'
        f"{html.escape(label)}</a>"
    )


def send_verification_email(
    *, recipient: str, username: str, verification_url: str
) -> bool:
    safe_username = html.escape(username)
    subject = "Verify your Library Tools email"
    html_body = _wrapper(f"""\
  <h1 style="margin:0 0 16px;font-size:22px;">Verify your email</h1>
  <p style="margin:0 0 8px;">Hi {safe_username},</p>
  <p style="margin:0;">Confirm this email address to use it for password recovery on your Library Tools account.</p>
  {_button(verification_url, "Verify email")}
  <p style="margin:0;font-size:12px;color:#746f62;">This link expires in 24 hours.</p>""")
    text_body = (
        f"Hi {username},\n\n"
        "Confirm this email address to use it for password recovery on your "
        "Library Tools account:\n\n"
        f"{verification_url}\n\n"
        "This link expires in 24 hours. If you didn't request this, you can "
        "safely ignore this email."
    )
    return _send(
        recipient=recipient, subject=subject, html_body=html_body, text_body=text_body
    )


def send_password_reset_email(
    *, recipient: str, username: str, reset_url: str
) -> bool:
    safe_username = html.escape(username)
    subject = "Reset your Library Tools password"
    html_body = _wrapper(f"""\
  <h1 style="margin:0 0 16px;font-size:22px;">Reset your password</h1>
  <p style="margin:0 0 8px;">Hi {safe_username},</p>
  <p style="margin:0;">We received a request to reset the password on your Library Tools account.</p>
  {_button(reset_url, "Reset password")}
  <p style="margin:0;font-size:12px;color:#746f62;">This link expires in 1 hour and can only be used once.</p>""")
    text_body = (
        f"Hi {username},\n\n"
        "We received a request to reset the password on your Library Tools "
        "account:\n\n"
        f"{reset_url}\n\n"
        "This link expires in 1 hour and can only be used once. If you "
        "didn't request this, you can safely ignore this email."
    )
    return _send(
        recipient=recipient, subject=subject, html_body=html_body, text_body=text_body
    )

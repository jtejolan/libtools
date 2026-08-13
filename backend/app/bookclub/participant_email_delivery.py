"""Branded transactional and facilitator email for participant accounts."""

import html

from bookclub.email_delivery import (
    BOOKCLUB_FROM_NAME,
    BOOKCLUB_URL,
    bookclub_document,
    bookclub_text_footer,
    email_button,
    message_content,
)
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
        "This link expires in 24 hours. If you did not create this account, "
        "you can ignore this email."
    )
    html_body = bookclub_document(
        title=subject,
        preheader=f"Confirm your email address to join {club_name}.",
        club_name=club_name,
        body_html=f"""\
<h1 style="margin:0 0 16px;font-family:Georgia,'Times New Roman',serif;font-size:28px;font-weight:600;">Confirm your email</h1>
<p style="margin:0 0 12px;font-size:15px;line-height:1.6;">Hi {html.escape(name)},</p>
<p style="margin:0;font-size:15px;line-height:1.6;">You’re joining <strong>{html.escape(club_name)}</strong> on Book Club. Confirm this address to finish setting up your account.</p>
{email_button(verification_url, "Confirm email address")}
<p style="margin:0;color:#746f62;font-size:12px;line-height:1.5;">This link goes to <strong>bookclub.libtools.app</strong> and expires in 24 hours.</p>""",
        footer_html='<p style="margin:0 0 12px;">If you did not create this account, no action is required.</p>',
    )
    return send_email(
        to=[recipient], subject=subject,
        text_body=f"{text_body}{bookclub_text_footer(club_name)}",
        html_body=html_body, from_name=BOOKCLUB_FROM_NAME,
    )


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
    html_body = bookclub_document(
        title=subject,
        preheader=f"Reset the password for your {club_name} Book Club account.",
        club_name=club_name,
        body_html=f"""\
<h1 style="margin:0 0 16px;font-family:Georgia,'Times New Roman',serif;font-size:28px;font-weight:600;">Reset your password</h1>
<p style="margin:0 0 12px;font-size:15px;line-height:1.6;">Hi {html.escape(name)},</p>
<p style="margin:0;font-size:15px;line-height:1.6;">We received a request to reset the password for your <strong>{html.escape(club_name)}</strong> account.</p>
{email_button(reset_url, "Reset password")}
<p style="margin:0;color:#746f62;font-size:12px;line-height:1.5;">This link goes to <strong>bookclub.libtools.app</strong>, expires in 1 hour, and can only be used once.</p>""",
        footer_html='<p style="margin:0 0 12px;">If you did not request a reset, no action is required.</p>',
    )
    return send_email(
        to=[recipient], subject=subject,
        text_body=f"{text_body}{bookclub_text_footer(club_name)}",
        html_body=html_body, from_name=BOOKCLUB_FROM_NAME,
    )


def send_password_changed_email(*, recipient: str, name: str, club_name: str) -> bool:
    subject = f"Your {club_name} password was changed"
    text_body = (
        f"Hi {name},\n\n"
        f"The password on your {club_name} account was just changed. If "
        "this wasn't you, use the password reset link on your club's page "
        "to secure your account."
    )
    html_body = bookclub_document(
        title=subject,
        preheader=f"The password for your {club_name} account was changed.",
        club_name=club_name,
        body_html=f"""\
<h1 style="margin:0 0 16px;font-family:Georgia,'Times New Roman',serif;font-size:28px;font-weight:600;">Password changed</h1>
<p style="margin:0 0 12px;font-size:15px;line-height:1.6;">Hi {html.escape(name)},</p>
<p style="margin:0;font-size:15px;line-height:1.6;">The password for your <strong>{html.escape(club_name)}</strong> account was just changed.</p>
<p style="margin:18px 0 0;font-size:14px;line-height:1.6;">If this was you, no further action is needed. If it wasn’t, visit your club page directly at <a href="{BOOKCLUB_URL}" style="color:#173f35;font-weight:700;">bookclub.libtools.app</a> and request a new password.</p>""",
        footer_html='<p style="margin:0 0 12px;">This is a security notification; it does not contain a sign-in link.</p>',
    )
    return send_email(
        to=[recipient], subject=subject,
        text_body=f"{text_body}{bookclub_text_footer(club_name)}",
        html_body=html_body, from_name=BOOKCLUB_FROM_NAME,
    )


def send_broadcast_email(
    *, recipient: str, subject: str, body: str, unsubscribe_url: str,
    club_name: str | None = None,
) -> bool:
    """A facilitator-authored broadcast. Sent one-at-a-time (not BCC'd like
    bookclub/email_delivery.send_reminder_batch's member reminders) so each
    recipient gets their own working, no-login-required unsubscribe link —
    see participant_unsubscribe.py.
    """
    text_body = (
        f"{body}{bookclub_text_footer(club_name)}\n\n"
        f"Stop receiving club broadcasts: {unsubscribe_url}"
    )
    html_body = bookclub_document(
        title=subject,
        preheader=subject,
        body_html=message_content(
            subject=subject, body=body, eyebrow="From your facilitator"
        ),
        club_name=club_name,
        footer_html=(
            '<p style="margin:0 0 12px;">You can '
            f'<a href="{html.escape(unsubscribe_url, quote=True)}" style="color:#746f62;">'
            'unsubscribe from club broadcasts</a> at any time.</p>'
        ),
    )
    return send_email(
        to=[recipient], subject=subject, text_body=text_body,
        html_body=html_body, from_name=BOOKCLUB_FROM_NAME,
        headers={"List-Unsubscribe": f"<{unsubscribe_url}>"},
    )

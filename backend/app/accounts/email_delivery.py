"""Email delivery for account messages, sent via Resend (https://resend.com).

The Resend transport itself (config, DELIVERY_CONFIGURED, the low-level
send call) lives in the shared `email_delivery` module so other packages
(e.g. bookclub) can reuse it. This module holds only the account-specific
HTML branding and message templates.

Templates follow standard HTML-email deliverability practices: a full
document (not a bare fragment) so strict clients render/parse consistently,
inline-only CSS (client-side <style> stripping is common), a table-based
button for Outlook's Word rendering engine, a hidden preheader so the inbox
preview snippet is meaningful, and a footer identifying the sender so the
message reads as legitimate transactional mail rather than an anonymous
blast. None of this substitutes for domain-level SPF/DKIM/DMARC — that's
configured in Resend's domain settings and DNS, not here.
"""

import html

from email_delivery import DELIVERY_CONFIGURED, send_email

SITE_URL = "https://libtools.app"
LOGO_URL = f"{SITE_URL}/static/assets/library-tools-logo-classic.png"

__all__ = ["DELIVERY_CONFIGURED", "send_verification_email", "send_password_changed_email", "send_password_reset_email"]


def _send(*, recipient: str, subject: str, html_body: str, text_body: str) -> bool:
    return send_email(
        to=[recipient], subject=subject, html_body=html_body, text_body=text_body
    )


DEFAULT_FOOTNOTE = "If you didn't request this, you can safely ignore this email."


def _document(
    *, title: str, preheader: str, body_html: str, footnote: str | None = DEFAULT_FOOTNOTE
) -> str:
    footnote_html = (
        f'<p style="margin:32px 0 0;font-size:12px;color:#746f62;">{html.escape(footnote)}</p>'
        if footnote
        else ""
    )
    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="light"/>
<meta name="supported-color-schemes" content="light"/>
<title>{html.escape(title)}</title>
</head>
<body style="margin:0;padding:0;background:#f4eedf;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;font-size:1px;line-height:1px;color:#f4eedf;">
  {html.escape(preheader)}
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4eedf;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="width:480px;max-width:100%;border-collapse:collapse;">
<tr><td style="background:#163e34;padding:28px 24px;text-align:center;border-radius:12px 12px 0 0;">
  <img src="{LOGO_URL}" width="44" height="47" alt="Library Tools" style="display:block;width:44px;height:47px;margin:0 auto;border:0;outline:none;text-decoration:none;"/>
</td></tr>
<tr><td style="font-family:-apple-system,Helvetica,Arial,sans-serif;padding:32px 24px;color:#183b33;background:#fffaf0;border-radius:0 0 12px 12px;">
  {body_html}
  {footnote_html}
  <p style="margin:20px 0 0;padding-top:16px;border-top:1px solid #e8e0cc;font-size:12px;color:#96907f;">
    Library Tools · <a href="{SITE_URL}" style="color:#96907f;">{SITE_URL.removeprefix("https://")}</a>
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    safe_url = html.escape(url)
    safe_label = html.escape(label)
    return f"""\
  <table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin:20px auto;">
  <tr><td style="border-radius:6px;background:#163e34;">
    <a href="{safe_url}" style="display:inline-block;padding:12px 20px;font-family:-apple-system,Helvetica,Arial,sans-serif;font-weight:600;font-size:15px;color:#fffaf0;text-decoration:none;">{safe_label}</a>
  </td></tr>
  </table>"""


def send_verification_email(
    *, recipient: str, username: str, verification_url: str
) -> bool:
    safe_username = html.escape(username)
    subject = "Welcome to Library Tools — verify your email"
    html_body = _document(
        title=subject,
        preheader="You're in! Take a look at what's available, then confirm your email to finish setting up.",
        body_html=f"""\
  <h1 style="margin:0 0 16px;font-size:22px;">Welcome to Library Tools</h1>
  <p style="margin:0 0 8px;">Hi {safe_username},</p>
  <p style="margin:0;">Your account is ready. Library Tools is a home for practical library software — with one account you get:</p>
  <ul style="margin:16px 0 0;padding-left:20px;font-size:14px;line-height:1.7;">
    <li><strong>Lendery</strong> — track lendable equipment, kits, and their components.</li>
    <li><strong>Book Club Manager</strong> — run clubs: members, meetings, attendance, and giveaways.</li>
    <li><strong>Storytime Studio</strong> — a planner for storytime resources and outlines, coming soon.</li>
  </ul>
  <p style="margin:20px 0 0;">Confirm this email address to finish setting up and enable password recovery.</p>
  {_button(verification_url, "Verify email")}
  <p style="margin:0;font-size:12px;color:#746f62;">This link expires in 24 hours.</p>""",
    )
    text_body = (
        f"Hi {username},\n\n"
        "Welcome to Library Tools — your account is ready. Library Tools is "
        "a home for practical library software. With one account you get:\n\n"
        "- Lendery — track lendable equipment, kits, and their components.\n"
        "- Book Club Manager — run clubs: members, meetings, attendance, "
        "and giveaways.\n"
        "- Storytime Studio — a planner for storytime resources and "
        "outlines, coming soon.\n\n"
        "Confirm this email address to finish setting up and enable "
        "password recovery:\n\n"
        f"{verification_url}\n\n"
        "This link expires in 24 hours. If you didn't request this, you can "
        "safely ignore this email.\n\n"
        f"Library Tools — {SITE_URL}"
    )
    return _send(
        recipient=recipient, subject=subject, html_body=html_body, text_body=text_body
    )


def send_password_changed_email(*, recipient: str, username: str) -> bool:
    safe_username = html.escape(username)
    subject = "Your Library Tools password was changed"
    reset_url = f"{SITE_URL}/forgot-password"
    html_body = _document(
        title=subject,
        preheader="Your Library Tools account password was just changed.",
        footnote=None,
        body_html=f"""\
  <h1 style="margin:0 0 16px;font-size:22px;">Password changed</h1>
  <p style="margin:0 0 8px;">Hi {safe_username},</p>
  <p style="margin:0;">The password on your Library Tools account was just changed.</p>
  <p style="margin:20px 0 0;font-size:14px;">If this was you, no further action is needed.</p>
  <p style="margin:8px 0 0;font-size:14px;">If you didn't make this change, reset your password right away:</p>
  {_button(reset_url, "Reset your password")}""",
    )
    text_body = (
        f"Hi {username},\n\n"
        "The password on your Library Tools account was just changed.\n\n"
        "If this was you, no further action is needed.\n\n"
        "If you didn't make this change, reset your password right away:\n\n"
        f"{reset_url}\n\n"
        f"Library Tools — {SITE_URL}"
    )
    return _send(
        recipient=recipient, subject=subject, html_body=html_body, text_body=text_body
    )


def send_password_reset_email(
    *, recipient: str, username: str, reset_url: str
) -> bool:
    safe_username = html.escape(username)
    subject = "Reset your Library Tools password"
    html_body = _document(
        title=subject,
        preheader="We received a request to reset the password on your Library Tools account.",
        body_html=f"""\
  <h1 style="margin:0 0 16px;font-size:22px;">Reset your password</h1>
  <p style="margin:0 0 8px;">Hi {safe_username},</p>
  <p style="margin:0;">We received a request to reset the password on your Library Tools account.</p>
  {_button(reset_url, "Reset password")}
  <p style="margin:0;font-size:12px;color:#746f62;">This link expires in 1 hour and can only be used once.</p>""",
    )
    text_body = (
        f"Hi {username},\n\n"
        "We received a request to reset the password on your Library Tools "
        "account:\n\n"
        f"{reset_url}\n\n"
        "This link expires in 1 hour and can only be used once. If you "
        "didn't request this, you can safely ignore this email.\n\n"
        f"Library Tools — {SITE_URL}"
    )
    return _send(
        recipient=recipient, subject=subject, html_body=html_body, text_body=text_body
    )

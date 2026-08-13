"""Recognizable, multipart email for facilitator-led book-club messages."""

import html
import re

from email_delivery import DELIVERY_CONFIGURED, send_email

BOOKCLUB_URL = "https://bookclub.libtools.app"
BOOKCLUB_LOGO_URL = f"{BOOKCLUB_URL}/static/assets/library-tools-logo-classic.png"
BOOKCLUB_FROM_NAME = "Book Club by Library Tools"

__all__ = [
    "DELIVERY_CONFIGURED",
    "bookclub_document",
    "bookclub_text_footer",
    "email_button",
    "message_content",
    "plain_text_html",
    "send_onboarding_email",
    "send_reminder_batch",
]


def plain_text_html(body: str) -> str:
    """Convert facilitator-authored plain text to conservative email HTML."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body.strip()) if part.strip()]
    return "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.65;">'
        f'{html.escape(paragraph).replace(chr(10), "<br/>")}</p>'
        for paragraph in paragraphs
    )


def email_button(url: str, label: str) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0;">
<tr><td style="border-radius:7px;background:#173f35;">
<a href="{html.escape(url, quote=True)}" style="display:inline-block;padding:13px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#fffaf1;font-size:15px;font-weight:700;text-decoration:none;">{html.escape(label)}</a>
</td></tr></table>"""


def message_content(*, subject: str, body: str, eyebrow: str) -> str:
    """Present editable plain-text templates within the branded visual shell."""
    return f"""\
<p style="margin:0 0 8px;color:#b96b39;font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;">{html.escape(eyebrow)}</p>
<h1 style="margin:0 0 20px;color:#173f35;font-family:Georgia,'Times New Roman',serif;font-size:30px;font-weight:600;line-height:1.12;">{html.escape(subject)}</h1>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;">
<tr><td style="padding:20px 21px;border:1px solid #e8dfcc;border-left:4px solid #d2713f;border-radius:10px;background:#fffdf8;">
{plain_text_html(body)}
</td></tr></table>"""


def bookclub_document(
    *, title: str, preheader: str, body_html: str, club_name: str | None = None,
    footer_html: str = "",
) -> str:
    identity = club_name or "Your book club"
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
<body style="margin:0;padding:0;background:#f3eddf;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;font-size:1px;line-height:1px;color:#f3eddf;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3eddf;">
<tr><td align="center" style="padding:28px 14px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;max-width:100%;border:1px solid #dfd5bf;border-collapse:separate;border-spacing:0;box-shadow:0 18px 44px rgba(23,63,53,.12);border-radius:16px;">
<tr><td height="6" style="height:6px;background:#d2713f;border-radius:15px 15px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:24px 28px;background:#173f35;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="64">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td width="10" height="34" style="width:10px;height:34px;background:#d2713f;border-radius:2px;">&nbsp;</td><td width="4"></td>
<td width="10" height="42" style="width:10px;height:42px;background:#e0af65;border-radius:2px;">&nbsp;</td><td width="4"></td>
<td width="10" height="37" style="width:10px;height:37px;background:#91a774;border-radius:2px;">&nbsp;</td>
</tr></table>
</td>
<td style="font-family:Georgia,'Times New Roman',serif;color:#fffaf1;font-size:24px;font-weight:bold;line-height:1.05;">Book Club<br/><span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#f1c894;font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;">{html.escape(identity)}</span></td>
<td width="42" align="right"><img src="{BOOKCLUB_LOGO_URL}" width="34" height="36" alt="Library Tools" style="display:block;width:34px;height:36px;border:0;opacity:.88;"/></td>
</tr></table>
</td></tr>
<tr><td style="padding:32px 30px;background:#fffaf1;color:#173f35;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
{body_html}
</td></tr>
<tr><td style="padding:20px 30px;background:#f7efdf;border-top:1px solid #e7deca;border-radius:0 0 15px 15px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#746f62;font-size:12px;line-height:1.55;">
{footer_html}
<strong style="color:#173f35;">Book Club by Library Tools</strong><br/>
This email was sent because you are a member of {html.escape(identity)}.<br/>
<a href="{BOOKCLUB_URL}" style="color:#746f62;">bookclub.libtools.app</a>
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def bookclub_text_footer(club_name: str | None = None) -> str:
    identity = club_name or "your book club"
    return (
        f"\n\n---\nBook Club by Library Tools\n"
        f"You received this email because you are a member of {identity}.\n"
        f"{BOOKCLUB_URL}"
    )


def send_onboarding_email(
    *, recipient: str, subject: str, body: str, club_name: str | None = None
) -> bool:
    html_body = bookclub_document(
        title=subject,
        preheader=subject,
        body_html=message_content(
            subject=subject, body=body, eyebrow="A note from your book club"
        ),
        club_name=club_name,
    )
    return send_email(
        to=[recipient], subject=subject,
        text_body=f"{body}{bookclub_text_footer(club_name)}", html_body=html_body,
        from_name=BOOKCLUB_FROM_NAME,
    )


def send_reminder_batch(
    *, recipients: list[str], subject: str, body: str,
    club_name: str | None = None,
) -> bool:
    if not recipients:
        return False
    html_body = bookclub_document(
        title=subject,
        preheader=subject,
        body_html=message_content(
            subject=subject, body=body, eyebrow="Meeting reminder"
        ),
        club_name=club_name,
    )
    text_body = f"{body}{bookclub_text_footer(club_name)}"
    results = [
        send_email(
            to=[recipient], subject=subject, text_body=text_body,
            html_body=html_body, from_name=BOOKCLUB_FROM_NAME,
        )
        for recipient in recipients
    ]
    return all(results)

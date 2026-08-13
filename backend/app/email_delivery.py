"""Shared outbound email delivery, sent via Resend (https://resend.com).

Configured through RESEND_API_KEY and RESEND_FROM_ADDRESS env vars. When
either is unset, DELIVERY_CONFIGURED is False and sends are skipped —
callers should handle that (e.g. falling back to a copy/paste flow, or
recovery codes for account emails).

This module holds only the low-level Resend transport. Product-specific
templates and branding live with their callers (e.g.
accounts/email_delivery.py's HTML-document wrapper for account messages,
bookclub/email_delivery.py's plain-text bookclub sends).
"""

import html
import logging
import os
from email.utils import parseaddr

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_ADDRESS = os.getenv("RESEND_FROM_ADDRESS")
RESEND_REPLY_TO = os.getenv("RESEND_REPLY_TO")

DELIVERY_CONFIGURED = bool(RESEND_API_KEY and RESEND_FROM_ADDRESS)


def _from_header() -> str | None:
    if not RESEND_FROM_ADDRESS:
        return None
    # A display name (not a bare address) reads as a real sender to both
    # spam filters and end users; add one if the env var didn't include it.
    if "<" in RESEND_FROM_ADDRESS:
        return RESEND_FROM_ADDRESS
    return f"Library Tools <{RESEND_FROM_ADDRESS}>"


def _from_header_with_name(from_name: str | None) -> str | None:
    if not RESEND_FROM_ADDRESS:
        return None
    if not from_name:
        return _from_header()
    _, address = parseaddr(RESEND_FROM_ADDRESS)
    return f"{from_name} <{address or RESEND_FROM_ADDRESS}>"


def _default_html(text_body: str) -> str:
    escaped = html.escape(text_body).replace("\n", "<br>")
    return f'<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;white-space:normal;">{escaped}</div>'


def send_email(
    *,
    to: list[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
    bcc: list[str] | None = None,
    from_name: str | None = None,
    headers: dict[str, str] | None = None,
) -> bool:
    if not DELIVERY_CONFIGURED:
        logger.info(
            "Email delivery is not configured; skipping send to %s", to
        )
        return False
    payload = {
        "from": _from_header_with_name(from_name),
        "to": to,
        "subject": subject,
        "html": html_body or _default_html(text_body),
        "text": text_body,
    }
    if bcc:
        payload["bcc"] = bcc
    if RESEND_REPLY_TO:
        payload["reply_to"] = [RESEND_REPLY_TO]
    if headers:
        payload["headers"] = headers
    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send email to %s via Resend", to)
        return False

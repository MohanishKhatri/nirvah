"""Approval email sending via Resend.

With no RESEND_API_KEY the emails are logged instead of sent, and the approval links are printed
so the flow stays clickable during local development.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"

BASE_STYLE = "font-family:Arial,Helvetica,sans-serif;background:#07080C;color:#E8EAF0;padding:32px;"
CARD_STYLE = "max-width:560px;margin:0 auto;background:#111318;border:1px solid #252A36;border-radius:14px;padding:28px;"
BTN_APPROVE = "display:inline-block;background:#3EC97A;color:#07080C;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:bold;"
BTN_REJECT = "display:inline-block;background:transparent;color:#EF4444;border:1px solid #EF4444;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:bold;"


async def _send(to_email: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
        logger.info("EMAIL (not sent, no RESEND_API_KEY)\n  to: %s\n  subject: %s", to_email, subject)
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.resend_from,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
        if res.status_code >= 300:
            logger.error("Resend rejected the email (%s): %s", res.status_code, res.text)
            return False
        return True
    except Exception:
        logger.exception("Could not send email to %s", to_email)
        return False


def _summary_rows(structured_fields: dict) -> str:
    rows = []
    for key, label in (
        ("purpose", "Purpose"),
        ("budget", "Budget"),
        ("attendees", "Attendees"),
        ("venue", "Venue"),
    ):
        value = structured_fields.get(key)
        if value in (None, "", 0):
            continue
        if key == "budget" and isinstance(value, (int, float)):
            value = f"&#8377;{int(value):,}"
        rows.append(
            f'<tr><td style="padding:6px 12px 6px 0;color:#6B7280;font-size:13px;">{label}</td>'
            f'<td style="padding:6px 0;color:#E8EAF0;font-size:13px;">{value}</td></tr>'
        )
    return "".join(rows)


def _shell(inner: str) -> str:
    return (
        f'<div style="{BASE_STYLE}"><div style="{CARD_STYLE}">'
        f'<p style="letter-spacing:4px;color:#6B7280;font-size:12px;margin:0 0 20px;">NIRVAH</p>'
        f"{inner}"
        f'<p style="color:#6B7280;font-size:11px;margin-top:28px;border-top:1px solid #252A36;padding-top:16px;">'
        "This link is unique to you. No login is required.</p>"
        "</div></div>"
    )


async def send_approval_email(
    to_email: str,
    token: str,
    label: str,
    brief: str,
    structured_fields: dict,
    reminder: bool = False,
) -> bool:
    approve_url = f"{settings.frontend_url}/approve/{token}?action=approve"
    reject_url = f"{settings.frontend_url}/approve/{token}?action=reject"

    heading = (
        f"Reminder — still awaiting your approval: {label}"
        if reminder
        else f"Action required: {label}"
    )

    inner = (
        f'<h2 style="margin:0 0 16px;font-size:19px;color:#F0C040;">{heading}</h2>'
        f'<p style="font-size:14px;line-height:1.6;color:#E8EAF0;margin:0 0 20px;">{brief}</p>'
        f'<table style="margin:0 0 24px;border-collapse:collapse;">{_summary_rows(structured_fields)}</table>'
        f'<p style="margin:0 0 8px;"><a href="{approve_url}" style="{BTN_APPROVE}">Approve</a>'
        f'&nbsp;&nbsp;<a href="{reject_url}" style="{BTN_REJECT}">Reject</a></p>'
    )

    logger.info("Approval link for %s: %s", label, approve_url)
    return await _send(to_email, f"[NIRVAH] {heading}", _shell(inner))


async def send_reminder_email(
    to_email: str, token: str, label: str, brief: str, structured_fields: dict
) -> bool:
    return await send_approval_email(
        to_email, token, label, brief, structured_fields, reminder=True
    )


async def send_rejection_notification(
    to_email: str, purpose: str, rejected_by: str, reason: str
) -> bool:
    inner = (
        '<h2 style="margin:0 0 16px;font-size:19px;color:#EF4444;">Your request was rejected</h2>'
        f'<p style="font-size:14px;line-height:1.6;margin:0 0 12px;">{purpose}</p>'
        f'<p style="font-size:14px;line-height:1.6;margin:0 0 12px;color:#6B7280;">Rejected by '
        f'<span style="color:#E8EAF0;">{rejected_by}</span></p>'
        f'<p style="font-size:14px;line-height:1.6;background:#151920;border:1px solid #252A36;'
        f'border-radius:10px;padding:14px;">{reason}</p>'
        '<p style="font-size:13px;color:#6B7280;margin-top:16px;">You can revise the request and '
        "submit it again.</p>"
    )
    return await _send(to_email, "[NIRVAH] Your request was rejected", _shell(inner))


async def send_approval_notification(to_email: str, purpose: str) -> bool:
    inner = (
        '<h2 style="margin:0 0 16px;font-size:19px;color:#3EC97A;">Your request is fully approved</h2>'
        f'<p style="font-size:14px;line-height:1.6;margin:0;">{purpose}</p>'
        '<p style="font-size:13px;color:#6B7280;margin-top:16px;">Every approver in the chain has '
        "signed off. No further action is needed.</p>"
    )
    return await _send(to_email, "[NIRVAH] Your request is approved", _shell(inner))

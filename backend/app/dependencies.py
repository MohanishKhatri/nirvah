from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def _verify_google_token(token: str) -> str:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    info = google_id_token.verify_oauth2_token(
        token, google_requests.Request(), settings.google_client_id or None
    )
    email = info.get("email", "")
    if not email:
        raise ValueError("token carries no email")
    return email


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """Returns the student's email. The Google ID token is the only credential students have."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if settings.dev_auth_bypass:
        return f"demo.student@{settings.allowed_email_domain}"

    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    try:
        email = _verify_google_token(token)
    except Exception:
        logger.exception("Google token verification failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token") from None

    domain = settings.allowed_email_domain.lower()
    if domain and not email.lower().endswith(f"@{domain}"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Sign-in is restricted to @{domain} accounts"
        )
    return email


async def require_admin(x_admin_password: str | None = Header(default=None)) -> bool:
    if not hmac.compare_digest(x_admin_password or "", settings.admin_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin password")
    return True

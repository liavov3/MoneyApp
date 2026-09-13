"""Private session resolution (PRIVATE_AUTH_V0_0_2).

Every resource still uses the server-resolved principal and ownership-as-404
from API_CONTRACT §3. Static bearer access is opt-in for local/tests only.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.errors import AppError
from app.models import PrivateSession

_BEARER_PREFIX = "bearer "
SESSION_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class Principal:
    """The authenticated, server-resolved current user. Opaque to the client."""

    user_id: str
    session_hash: str | None = None
    expires_at: datetime | None = None


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Parse `Authorization: Bearer <token>` (scheme case-insensitive).

    Returns the raw token, or None if the header is absent/malformed.
    """
    if not authorization:
        return None
    if not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX):].strip()
    return token or None


def cookie_name() -> str:
    return "__Host-moneysaver_session" if get_settings().production else "moneysaver_session"


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_browser_origin(request: Request) -> None:
    settings = get_settings()
    expected = settings.browser_origin
    if not expected and not settings.production:
        expected = str(request.base_url).rstrip("/")
    if (not expected or request.headers.get("origin") != expected or
            request.headers.get("x-moneysaver-client") != "web"):
        raise AppError(code="unsupported_operation")


def presented_session(request: Request) -> str | None:
    # An explicitly supplied Authorization header cannot fall back to a cookie.
    if "authorization" in request.headers:
        return _extract_bearer_token(request.headers.get("authorization"))
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_browser_origin(request)
    return request.cookies.get(cookie_name())


async def require_principal(request: Request, db: AsyncSession = Depends(get_session)) -> Principal:
    """Resolve only the configured owner; resource ownership filters stay intact."""
    settings = get_settings()
    bearer = _extract_bearer_token(request.headers.get("authorization"))
    if (settings.allow_dev_bearer and not settings.production and
            settings.dev_bearer_token and bearer and secrets.compare_digest(
                bearer.encode("utf-8"), settings.dev_bearer_token.encode("utf-8"))):
        return Principal(user_id=settings.dev_user_id)

    if "authorization" not in request.headers and not request.cookies.get(cookie_name()):
        raise AppError(code="unauthorized")
    token = presented_session(request)
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise AppError(code="unauthorized")
    try:
        row = await db.scalar(select(PrivateSession).where(
            PrivateSession.token_hash == token_digest(token),
            PrivateSession.user_id == settings.owner_user_id,
            PrivateSession.expires_at > datetime.now(timezone.utc),
        ))
    except SQLAlchemyError:
        raise AppError(code="backend_unavailable") from None
    if row is None:
        raise AppError(code="unauthorized")
    return Principal(user_id=row.user_id, session_hash=row.token_hash, expires_at=row.expires_at)

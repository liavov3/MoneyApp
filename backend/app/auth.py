"""Server-side principal resolution (API_CONTRACT §3).

v0.0.1 is single-user, local/dev mode. The client presents a static dev bearer
token (`Authorization: Bearer <token>`); the server resolves it to the single
dev principal and scopes every query to the resolved `user_id`. The client
NEVER supplies `user_id` — there is no body field or query parameter through
which a client can name a different user (firm rule, §3).

Missing/invalid token -> `401 unauthorized` with the standard error envelope
(§5). The token itself is never logged (QA-10-06).

When real auth lands, ONLY this resolution layer changes; resource routes and
response shapes do not (the reason `user_id` is server-resolved and absent from
every payload).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Request

from app.config import get_settings
from app.errors import AppError

_BEARER_PREFIX = "bearer "


@dataclass(frozen=True)
class Principal:
    """The authenticated, server-resolved current user. Opaque to the client."""

    user_id: str


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


def require_principal(request: Request) -> Principal:
    """FastAPI dependency: resolve the current principal or raise 401.

    A valid dev token resolves to the single server-side dev user. The token is
    compared in constant time. The token value is never logged or echoed.
    """
    settings = get_settings()
    expected = settings.dev_bearer_token
    presented = _extract_bearer_token(request.headers.get("Authorization"))

    # No server token configured, or no/blank token presented, or mismatch.
    if not expected or not presented or not secrets.compare_digest(
        presented, expected
    ):
        raise AppError(code="unauthorized")

    # user_id is resolved here, server-side — never from the client.
    return Principal(user_id=settings.dev_user_id)

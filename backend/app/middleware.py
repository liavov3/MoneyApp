"""Request middleware: assign a request_id and emit a privacy-safe access log."""

from __future__ import annotations

import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_utils import duration_bucket, log_event
from app.config import get_settings


def _new_request_id() -> str:
    return "req_" + secrets.token_hex(8)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = _new_request_id()
        request.state.request_id = request_id
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Request-ID"] = request_id
        # API bodies and the application document must not be retained after
        # logout by a browser cache or shared proxy. No service worker is used.
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        if get_settings().production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        # Privacy-safe access log: ids/enums/buckets only — never body content.
        log_event(
            "request",
            request_id=request_id,
            endpoint=getattr(request.scope.get("route"), "path", "unmatched"),
            method=request.method,
            status=response.status_code,
            duration_bucket=duration_bucket(elapsed),
        )
        return response

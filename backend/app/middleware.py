"""Request middleware: assign a request_id and emit a privacy-safe access log."""

from __future__ import annotations

import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_utils import duration_bucket, log_event


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
        # Privacy-safe access log: ids/enums/buckets only — never body content.
        log_event(
            "request",
            request_id=request_id,
            endpoint=request.url.path,
            method=request.method,
            status=response.status_code,
            duration_bucket=duration_bucket(elapsed),
        )
        return response

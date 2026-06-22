"""GET /api/v1/health — app + DB reachability.

Returns 200 with {"status": "ok", "db": "reachable"} when the database
responds to a trivial `SELECT 1`. If the DB is unreachable, raises the standard
`backend_unavailable` (503) envelope (QA-11-07). Logs only the safe shape:
request id, endpoint, status, duration bucket, db_reachable boolean — never
credentials, DSN, PII, or exception text (QA-10-06 / QA-10-10).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", "req_unknown")
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        # Do NOT include the exception text (may carry DSN/host details).
        log_event(
            "health_check",
            request_id=request_id,
            endpoint="/api/v1/health",
            status=503,
            db_reachable=False,
        )
        raise AppError(code="backend_unavailable") from None

    log_event(
        "health_check",
        request_id=request_id,
        endpoint="/api/v1/health",
        status=200,
        db_reachable=True,
    )
    return {"status": "ok", "db": "reachable"}

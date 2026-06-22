"""GET /api/v1/categories — list the 22 seeded system categories (API_CONTRACT §6).

Read-only in v0.0.1. Auth required (resolved principal). System categories
(`user_id IS NULL`) are shared and read-only, so the response is identical for
any principal (QA-13-10). The client filters locally to `layer ==
consumer_spending` for Quick Add; this endpoint returns ALL 22.

Returned fields per category exactly match the contract:
  id, key, label_en, label_he, layer,
  included_in_actual_spending, included_in_cash_flow, is_system.
`included_in_committed_projection` is intentionally omitted (always false by
schema invariant — §6).

Privacy: logs only the safe shape (request id, endpoint, status, row count).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event

router = APIRouter()


class CategoryOut(BaseModel):
    """A single system category as defined by API_CONTRACT §6."""

    id: str
    key: str | None
    label_en: str
    label_he: str | None
    layer: str
    included_in_actual_spending: bool
    included_in_cash_flow: bool
    is_system: bool


class CategoryListResponse(BaseModel):
    items: list[CategoryOut]


# System categories only (user_id IS NULL), with the exact contract fields.
# Deterministic order: consumer_spending first (layer DESC), then key.
_SELECT_SYSTEM_CATEGORIES = text(
    """
    SELECT id::text AS id, key, label_en, label_he, layer,
           included_in_actual_spending, included_in_cash_flow, is_system
    FROM categories
    WHERE user_id IS NULL AND is_system = true
    ORDER BY layer DESC, key ASC
    """
)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    request: Request,
    principal: Principal = Depends(require_principal),
) -> CategoryListResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (await session.execute(_SELECT_SYSTEM_CATEGORIES)).mappings().all()
    except Exception:
        # Never include exception text (may carry DSN/host details).
        log_event(
            "list_categories",
            request_id=request_id,
            endpoint="/api/v1/categories",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    items = [CategoryOut(**row) for row in rows]
    log_event(
        "list_categories",
        request_id=request_id,
        endpoint="/api/v1/categories",
        status=200,
        row_count=len(items),
    )
    return CategoryListResponse(items=items)

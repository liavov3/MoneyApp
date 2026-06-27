"""GET /api/v1/merchants/recent — recent merchant chips for Quick Add (§ contract).

Read-only in this slice. Auth required; strictly principal-scoped — only the
server-resolved user's merchants are returned, ordered most-recently-used first
(`merchants.updated_at DESC`, on the `(user_id, updated_at DESC)` index). Each
item carries the contract's category-suggestion fields; in v0.0.1 the only
resolvable §9 level is the stored merchant default (`default_category_id`,
currently unset), so `suggested_category_*` is null until a later slice
populates it. No aliases, suggestions engine, fuzzy, or rules here.

Privacy: `display_name` (and the normalized key) are sensitive and NEVER logged
(MERCHANT_NORMALIZATION_SPEC §14); logs carry only request id / endpoint /
status / row count.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event

router = APIRouter()

_DEFAULT_LIMIT = 8
_MAX_LIMIT = 20


class RecentMerchantOut(BaseModel):
    merchant_id: str
    display_name: str
    suggested_category_id: str | None
    suggested_category_key: str | None
    suggested_category_source: str | None
    last_used_at: str


class RecentMerchantsResponse(BaseModel):
    items: list[RecentMerchantOut]


def _rfc3339(dt: datetime) -> str:
    """RFC 3339 UTC with a Z suffix, seconds precision (API_CONTRACT §4)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Principal-scoped; most-recent-first with id as a deterministic tiebreaker.
# LEFT JOIN surfaces the merchant-default category suggestion (§9 lowest level);
# higher levels (rules / recent-memory) are deferred to a later slice.
_SELECT_RECENT = text(
    """
    SELECT m.id::text AS merchant_id, m.display_name,
           m.default_category_id::text AS suggested_category_id,
           c.key AS suggested_category_key,
           CASE WHEN m.default_category_id IS NOT NULL
                THEN 'merchant_default' END AS suggested_category_source,
           m.updated_at AS last_used_at
    FROM merchants m
    LEFT JOIN categories c ON c.id = m.default_category_id
    WHERE m.user_id = :user_id
    ORDER BY m.updated_at DESC, m.id DESC
    LIMIT :limit
    """
)


@router.get("/merchants/recent", response_model=RecentMerchantsResponse)
async def recent_merchants(
    request: Request,
    principal: Principal = Depends(require_principal),
    limit: int = Query(default=_DEFAULT_LIMIT),
) -> RecentMerchantsResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    # Clamp to [1, 20] (contract default 8, max 20).
    page_limit = max(1, min(int(limit), _MAX_LIMIT))

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (
                await session.execute(
                    _SELECT_RECENT,
                    {"user_id": principal.user_id, "limit": page_limit},
                )
            ).mappings().all()
    except Exception:
        log_event(
            "recent_merchants",
            request_id=request_id,
            endpoint="/api/v1/merchants/recent",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    items = [
        RecentMerchantOut(
            merchant_id=r["merchant_id"],
            display_name=r["display_name"],
            suggested_category_id=r["suggested_category_id"],
            suggested_category_key=r["suggested_category_key"],
            suggested_category_source=r["suggested_category_source"],
            last_used_at=_rfc3339(r["last_used_at"]),
        )
        for r in rows
    ]

    # Privacy-safe log: row count only — never display_name or any merchant text.
    log_event(
        "recent_merchants",
        request_id=request_id,
        endpoint="/api/v1/merchants/recent",
        status=200,
        user_id=principal.user_id,
        row_count=len(items),
    )
    return RecentMerchantsResponse(items=items)

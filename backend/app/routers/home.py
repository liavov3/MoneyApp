"""GET /api/v1/home — the one-call Home dashboard (API_CONTRACT §13).

Returns the month's ACTUAL spend (Layer A, from `transactions`) and the
PROJECTED commitments (Layer B, from `recurring_expense_templates`) as DISTINCT
fields inside `known_this_month` — never a single blended total (firm rule;
CATEGORY_TAXONOMY §12). Every query is scoped to the server-resolved principal
(API_CONTRACT §3); `user_id` is never read from the client.

Money is signed integer agorot. Headline figures (`spent_so_far_minor`,
`committed_amount_minor`, category/known totals) are returned as non-negative
magnitudes; the per-row `amount_minor` in `recent_transactions` /
`upcoming_commitments` echoes the stored signed value (expense → negative), as
the contract examples show.

Privacy (API_CONTRACT §15): logs carry ids/counts only — never amount, note,
merchant text, or template name. The template `name` is never echoed either; the
payload exposes only `name_present` (schema §10 query 5).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event
from app.routers.transactions import _month_bounds

router = APIRouter()

# "Last few entries" recall list (schema §10 query 3 — N unspecified by the
# contract; 10 is a deterministic default, adjustable if the UX pins a number).
_RECENT_LIMIT = 10


class CategoryTotal(BaseModel):
    category_id: str
    category_key: str | None
    label_en: str
    total_minor: int


class RecentTxn(BaseModel):
    id: str
    amount_minor: int
    currency: str
    merchant_display_name: str | None
    category_key: str | None
    occurred_on: str
    is_uncategorized: bool


class UpcomingCommitment(BaseModel):
    template_id: str
    name_present: bool
    category_key: str | None
    amount_minor: int
    next_expected_date: str


class KnownThisMonth(BaseModel):
    spent_actual_minor: int
    committed_projected_minor: int


class HomeResponse(BaseModel):
    month: str
    currency: str
    spent_so_far_minor: int
    top_category: CategoryTotal | None
    category_totals: list[CategoryTotal]
    recent_transactions: list[RecentTxn]
    uncategorized_count: int
    upcoming_commitments: list[UpcomingCommitment]
    committed_amount_minor: int
    known_this_month: KnownThisMonth
    warnings: list[dict] = []


# Layer A spend filter shared by the headline (1) and per-category ranking (2):
# manual expenses, not card settlements, in-month, where the category counts as
# actual spending OR is uncategorized (uncategorized expenses ARE real spend).
_SPENT_SO_FAR = text(
    """
    SELECT COALESCE(SUM(ABS(t.amount_minor)), 0) AS spent
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    WHERE t.user_id = :u
      AND t.source = 'manual'
      AND t.transaction_type = 'expense'
      AND t.is_card_settlement = false
      AND t.occurred_on >= :start AND t.occurred_on < :end
      AND (t.category_id IS NULL OR c.included_in_actual_spending = true)
    """
)

# Same spend filter but category-only, grouped and ranked. Uncategorized is
# excluded (it is not a category). Tie-breaker: category_key ASC (deterministic;
# the contract does not specify one).
_CATEGORY_TOTALS = text(
    """
    SELECT t.category_id::text AS category_id, c.key AS category_key,
           c.label_en AS label_en, SUM(ABS(t.amount_minor)) AS total_minor
    FROM transactions t
    JOIN categories c ON c.id = t.category_id
    WHERE t.user_id = :u
      AND t.source = 'manual'
      AND t.transaction_type = 'expense'
      AND t.is_card_settlement = false
      AND t.occurred_on >= :start AND t.occurred_on < :end
      AND c.included_in_actual_spending = true
    GROUP BY t.category_id, c.key, c.label_en
    ORDER BY SUM(ABS(t.amount_minor)) DESC, c.key ASC
    """
)

# Recent recall list — ALL-TIME, not month-scoped (schema §10 query 3 has no
# month filter): a user who just logged a purchase sees it even when viewing a
# different month.
_RECENT = text(
    """
    SELECT t.id::text AS id, t.amount_minor, t.currency,
           m.display_name AS merchant_display_name, c.key AS category_key,
           t.occurred_on::text AS occurred_on,
           (t.category_id IS NULL) AS is_uncategorized
    FROM transactions t
    LEFT JOIN merchants m ON m.id = t.merchant_id
    LEFT JOIN categories c ON c.id = t.category_id
    WHERE t.user_id = :u
    ORDER BY t.occurred_on DESC, t.created_at DESC
    LIMIT :n
    """
)

# "Needs a category" review for the month (schema §10 query 4): any null-category
# row, regardless of transaction_type.
_UNCATEGORIZED_COUNT = text(
    """
    SELECT COUNT(*) AS n
    FROM transactions t
    WHERE t.user_id = :u
      AND t.category_id IS NULL
      AND t.occurred_on >= :start AND t.occurred_on < :end
    """
)

# Layer B projection (schema §10 query 5): active, projecting templates due in
# the month. `committed_amount_minor` is derived in Python as the magnitude sum.
# The template name is sensitive — only its presence is exposed.
_UPCOMING = text(
    """
    SELECT rt.id::text AS template_id, (rt.name IS NOT NULL) AS name_present,
           c.key AS category_key, rt.amount_minor,
           rt.next_expected_date::text AS next_expected_date
    FROM recurring_expense_templates rt
    JOIN categories c ON c.id = rt.category_id
    WHERE rt.user_id = :u
      AND rt.is_active = true
      AND rt.counts_in_projection = true
      AND rt.next_expected_date >= :start AND rt.next_expected_date < :end
    ORDER BY rt.next_expected_date ASC, rt.id ASC
    """
)


@router.get("/home", response_model=HomeResponse)
async def get_home(
    request: Request,
    principal: Principal = Depends(require_principal),
    month: str | None = Query(default=None),
) -> HomeResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # Default to the server's current month; validate `YYYY-MM` (422 on bad).
    month_str = month if month is not None else date.today().strftime("%Y-%m")
    start, end = _month_bounds(month_str)  # raises 422 validation_error

    bounds = {"u": principal.user_id, "start": start, "end": end}
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            currency = (
                await session.execute(
                    text("SELECT base_currency FROM users WHERE id = :u"),
                    {"u": principal.user_id},
                )
            ).scalar_one_or_none() or "ILS"

            spent = (await session.execute(_SPENT_SO_FAR, bounds)).scalar_one()
            cat_rows = (await session.execute(_CATEGORY_TOTALS, bounds)).mappings().all()
            recent_rows = (
                await session.execute(
                    _RECENT, {"u": principal.user_id, "n": _RECENT_LIMIT}
                )
            ).mappings().all()
            uncategorized_count = (
                await session.execute(_UNCATEGORIZED_COUNT, bounds)
            ).scalar_one()
            upcoming_rows = (await session.execute(_UPCOMING, bounds)).mappings().all()
    except AppError:
        raise
    except Exception:
        log_event(
            "home", request_id=request_id, endpoint="/api/v1/home", status=503
        )
        raise AppError(code="backend_unavailable") from None

    category_totals = [
        CategoryTotal(
            category_id=r["category_id"],
            category_key=r["category_key"],
            label_en=r["label_en"],
            total_minor=int(r["total_minor"]),
        )
        for r in cat_rows
    ]
    top_category = category_totals[0] if category_totals else None

    recent_transactions = [
        RecentTxn(
            id=r["id"],
            amount_minor=r["amount_minor"],
            currency=r["currency"],
            merchant_display_name=r["merchant_display_name"],
            category_key=r["category_key"],
            occurred_on=r["occurred_on"],
            is_uncategorized=r["is_uncategorized"],
        )
        for r in recent_rows
    ]

    upcoming_commitments = [
        UpcomingCommitment(
            template_id=r["template_id"],
            name_present=r["name_present"],
            category_key=r["category_key"],
            amount_minor=r["amount_minor"],
            next_expected_date=r["next_expected_date"],
        )
        for r in upcoming_rows
    ]
    committed = sum(abs(r["amount_minor"]) for r in upcoming_rows)

    spent = int(spent)
    # Privacy-safe log: counts only — never amounts, merchant/category text.
    log_event(
        "home",
        request_id=request_id,
        endpoint="/api/v1/home",
        status=200,
        user_id=principal.user_id,
        row_count=len(recent_transactions),
        count=int(uncategorized_count),  # uncategorized review count (§15 safe)
    )

    return HomeResponse(
        month=month_str,
        currency=currency,
        spent_so_far_minor=spent,
        top_category=top_category,
        category_totals=category_totals,
        recent_transactions=recent_transactions,
        uncategorized_count=int(uncategorized_count),
        upcoming_commitments=upcoming_commitments,
        committed_amount_minor=committed,
        known_this_month=KnownThisMonth(
            spent_actual_minor=spent, committed_projected_minor=committed
        ),
        warnings=[],  # ponytail: optional non-blocking notes; add when UX pins a threshold
    )

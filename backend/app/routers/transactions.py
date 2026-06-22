"""POST /api/v1/transactions/quick-add — create one manual transaction.

This slice implements the AMOUNT-ONLY subset of API_CONTRACT §8 / §14: amount is
the only required field; merchant matching/creation, category assignment, rules,
duplicate/large-amount warnings, and list/edit/delete are intentionally NOT
implemented yet. Save-first: a valid amount-only request persists immediately.

Auth required (API_CONTRACT §3). `user_id` is server-resolved from the dev
principal — never read from the client body (a client-supplied `user_id` is
ignored via `extra="ignore"`). Money is stored as signed integer agorot
(app/money.py). Privacy: amount, note, and raw input are NEVER logged.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event
from app.money import parse_amount_to_minor

router = APIRouter()

_VALID_TYPES = {"expense", "income", "refund", "adjustment"}
# Reject dates more than ~1 day in the future (typo guard; §14). Backdating ok.
_MAX_FUTURE_DAYS = 1


class QuickAddRequest(BaseModel):
    # Ignore any unknown/forbidden fields (e.g. a client-supplied user_id or the
    # not-yet-implemented merchant_input/merchant_id/category_id) — never trusted.
    model_config = ConfigDict(extra="ignore")

    # JSON number or decimal string; parsed via Decimal (app/money.py).
    amount: str | int | float | None = None
    transaction_type: str = "expense"
    occurred_on: str | None = None
    currency: str = "ILS"
    note: str | None = None


class TransactionOut(BaseModel):
    id: str
    amount_minor: int
    currency: str
    transaction_type: str
    source: str
    merchant_id: str | None
    merchant_display_name: str | None
    category_id: str | None
    category_key: str | None
    occurred_on: str
    note: str | None
    is_card_settlement: bool
    created_at: str
    updated_at: str


class QuickAddResponse(BaseModel):
    transaction: TransactionOut
    warnings: list[dict] = []
    category_suggestion: dict | None = None
    rule_prompt: dict = {"offer": False}
    alias_suggestion: dict | None = None


def _field_error(field: str, code: str, message: str) -> AppError:
    return AppError(
        code="validation_error",
        field_errors=[{"field": field, "code": code, "message": message}],
    )


def _resolve_occurred_on(raw: str | None) -> date:
    if raw is None:
        return date.today()  # server's current date (§14 date defaulting)
    try:
        parsed = date.fromisoformat(raw)
    except (ValueError, TypeError):
        raise _field_error("occurred_on", "invalid_date", "Enter a valid date.") from None
    if parsed > date.today() + timedelta(days=_MAX_FUTURE_DAYS):
        raise _field_error("occurred_on", "invalid_date", "That date is in the future.")
    return parsed


def _rfc3339(dt: datetime) -> str:
    """RFC 3339 UTC with a Z suffix, seconds precision (API_CONTRACT §4)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_INSERT_SQL = text(
    """
    INSERT INTO transactions
        (user_id, amount_minor, currency, transaction_type, source,
         occurred_on, note)
    VALUES
        (:user_id, :amount_minor, :currency, :transaction_type, 'manual',
         :occurred_on, :note)
    RETURNING id::text AS id, amount_minor, currency, transaction_type, source,
              merchant_id::text AS merchant_id, category_id::text AS category_id,
              note, occurred_on::text AS occurred_on, is_card_settlement,
              created_at, updated_at
    """
)


@router.post(
    "/transactions/quick-add",
    response_model=QuickAddResponse,
    status_code=status.HTTP_201_CREATED,
)
async def quick_add(
    request: Request,
    body: QuickAddRequest,
    principal: Principal = Depends(require_principal),
) -> QuickAddResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # --- validate (nothing persisted on failure) ---------------------------- #
    ttype = body.transaction_type
    if ttype not in _VALID_TYPES:
        raise _field_error("transaction_type", "invalid_enum", "Invalid transaction type.")

    currency = body.currency
    if not isinstance(currency, str) or len(currency) != 3:
        raise _field_error("currency", "invalid_currency", "Invalid currency code.")

    occurred_on = _resolve_occurred_on(body.occurred_on)
    amount_minor = parse_amount_to_minor(body.amount, ttype)  # raises 422 on bad input

    # --- persist (save-first) ----------------------------------------------- #
    params = {
        "user_id": principal.user_id,  # server-resolved ONLY
        "amount_minor": amount_minor,
        "currency": currency,
        "transaction_type": ttype,
        "occurred_on": occurred_on,
        "note": body.note,
    }
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            row = (await session.execute(_INSERT_SQL, params)).mappings().one()
            await session.commit()
    except Exception:
        # Never include exception text or the amount/note (privacy + DSN safety).
        log_event(
            "quick_add",
            request_id=request_id,
            endpoint="/api/v1/transactions/quick-add",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    txn = TransactionOut(
        id=row["id"],
        amount_minor=row["amount_minor"],
        currency=row["currency"],
        transaction_type=row["transaction_type"],
        source=row["source"],
        merchant_id=row["merchant_id"],
        merchant_display_name=None,  # merchant resolution not in this slice
        category_id=row["category_id"],
        category_key=None,  # category assignment not in this slice
        occurred_on=row["occurred_on"],
        note=row["note"],
        is_card_settlement=row["is_card_settlement"],
        created_at=_rfc3339(row["created_at"]),
        updated_at=_rfc3339(row["updated_at"]),
    )

    # Privacy-safe log: ids/status only — never amount, note, or raw input.
    log_event(
        "quick_add",
        request_id=request_id,
        endpoint="/api/v1/transactions/quick-add",
        status=201,
        user_id=principal.user_id,
        transaction_id=txn.id,
    )

    return QuickAddResponse(transaction=txn)

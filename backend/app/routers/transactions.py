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

import base64
import binascii
import json
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
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


# =========================================================================== #
# GET /transactions — list the principal's transactions (API_CONTRACT §9).
# =========================================================================== #

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100


class TransactionListResponse(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None = None


# Shared projection for a transaction row + display joins (list and single read).
# `raw_merchant_input` is intentionally NOT selected — sensitive, never returned
# (API_CONTRACT §9, GET /transactions/{id}).
_TXN_SELECT = (
    "t.id::text AS id, t.amount_minor, t.currency, t.transaction_type, "
    "t.source, t.merchant_id::text AS merchant_id, "
    "m.display_name AS merchant_display_name, "
    "t.category_id::text AS category_id, c.key AS category_key, "
    "t.occurred_on::text AS occurred_on, t.note, t.is_card_settlement, "
    "t.created_at, t.updated_at "
    "FROM transactions t "
    "LEFT JOIN merchants m ON m.id = t.merchant_id "
    "LEFT JOIN categories c ON c.id = t.category_id"
)


def _row_to_transaction_out(r) -> TransactionOut:
    return TransactionOut(
        id=r["id"],
        amount_minor=r["amount_minor"],
        currency=r["currency"],
        transaction_type=r["transaction_type"],
        source=r["source"],
        merchant_id=r["merchant_id"],
        merchant_display_name=r["merchant_display_name"],
        category_id=r["category_id"],
        category_key=r["category_key"],
        occurred_on=r["occurred_on"],
        note=r["note"],
        is_card_settlement=r["is_card_settlement"],
        created_at=_rfc3339(r["created_at"]),
        updated_at=_rfc3339(r["updated_at"]),
    )


def _month_bounds(month: str) -> tuple[date, date]:
    """Return [start, end) dates for a `YYYY-MM` month, or raise 422."""
    parts = month.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise _field_error("month", "invalid_month", "Use YYYY-MM.")
    try:
        year, mon = int(parts[0]), int(parts[1])
        start = date(year, mon, 1)
    except (ValueError, TypeError):
        raise _field_error("month", "invalid_month", "Use YYYY-MM.") from None
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


def _encode_cursor(occurred_on: str, created_at: datetime, txn_id: str) -> str:
    payload = json.dumps(
        {"o": occurred_on, "c": created_at.isoformat(), "id": txn_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[date, datetime, str]:
    """Decode an opaque cursor into typed (occurred_on, created_at, id) bounds.

    Returns native date/datetime objects so the asyncpg driver binds them as
    `date`/`timestamptz` (it rejects bare strings for those types).
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw)
        return (
            date.fromisoformat(str(data["o"])),
            datetime.fromisoformat(str(data["c"])),
            str(data["id"]),
        )
    except (binascii.Error, ValueError, KeyError, TypeError):
        raise _field_error("cursor", "invalid_cursor", "Invalid cursor.") from None


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    request: Request,
    principal: Principal = Depends(require_principal),
    month: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    uncategorized: bool | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    cursor: str | None = Query(default=None),
) -> TransactionListResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # --- validate filters ---------------------------------------------------- #
    if category_id is not None and uncategorized:
        raise _field_error(
            "uncategorized", "conflicting_filters",
            "category_id and uncategorized are mutually exclusive.",
        )

    # clamp limit to [1, 100] (contract default 50, max 100).
    page_limit = max(1, min(int(limit), _MAX_LIMIT))

    # WHERE clause scoped to the server-resolved principal — never the client.
    where = ["t.user_id = :user_id"]
    params: dict = {"user_id": principal.user_id}

    if month is not None:
        start, end = _month_bounds(month)
        where.append("t.occurred_on >= :m_start AND t.occurred_on < :m_end")
        params["m_start"] = start
        params["m_end"] = end

    if uncategorized:
        where.append("t.category_id IS NULL")
    elif category_id is not None:
        where.append("t.category_id = CAST(:category_id AS uuid)")
        params["category_id"] = category_id

    if cursor is not None:
        c_o, c_c, c_id = _decode_cursor(cursor)
        # Keyset: rows strictly "after" (older than) the cursor in DESC order.
        where.append(
            "(t.occurred_on, t.created_at, t.id) < "
            "(CAST(:c_o AS date), CAST(:c_c AS timestamptz), CAST(:c_id AS uuid))"
        )
        params.update({"c_o": c_o, "c_c": c_c, "c_id": c_id})

    # Fetch one extra row to detect whether a next page exists.
    params["lim"] = page_limit + 1
    sql = text(
        f"SELECT {_TXN_SELECT} "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY t.occurred_on DESC, t.created_at DESC, t.id DESC "
        "LIMIT :lim"
    )

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (await session.execute(sql, params)).mappings().all()
    except Exception:
        log_event(
            "list_transactions",
            request_id=request_id,
            endpoint="/api/v1/transactions",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    has_more = len(rows) > page_limit
    rows = rows[:page_limit]

    items = [_row_to_transaction_out(r) for r in rows]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last["occurred_on"], last["created_at"], last["id"])

    # Privacy-safe log: row count only — never amount, note, or merchant text.
    log_event(
        "list_transactions",
        request_id=request_id,
        endpoint="/api/v1/transactions",
        status=200,
        user_id=principal.user_id,
        row_count=len(items),
    )

    return TransactionListResponse(items=items, next_cursor=next_cursor)


# =========================================================================== #
# GET /transactions/{id} — single read, ownership-scoped (API_CONTRACT §9).
# =========================================================================== #

_SELECT_BY_ID = text(
    f"SELECT {_TXN_SELECT} WHERE t.id = :id AND t.user_id = :user_id"
)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    request: Request,
    transaction_id: str,
    principal: Principal = Depends(require_principal),
) -> TransactionOut:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # A non-UUID id cannot correspond to any row. Report 404 (never a format
    # error) so the response stays generic and leaks nothing about existence.
    try:
        uuid.UUID(transaction_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            row = (
                await session.execute(
                    _SELECT_BY_ID,
                    {"id": transaction_id, "user_id": principal.user_id},
                )
            ).mappings().one_or_none()
    except Exception:
        log_event(
            "get_transaction",
            request_id=request_id,
            endpoint="/api/v1/transactions/{id}",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    # Missing OR owned by another principal -> identical generic 404 (no leak).
    if row is None:
        raise AppError(code="not_found")

    txn = _row_to_transaction_out(row)
    # Privacy-safe log: ids/status only — never amount, note, or merchant text.
    log_event(
        "get_transaction",
        request_id=request_id,
        endpoint="/api/v1/transactions/{id}",
        status=200,
        user_id=principal.user_id,
        transaction_id=txn.id,
    )
    return txn

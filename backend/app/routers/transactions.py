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

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.category_rules import fetch_active_rules, resolve_suggestion
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event
from app.merchants import clean_raw, display_form, normalize_merchant_name
from app.money import parse_amount_to_minor

router = APIRouter()

_VALID_TYPES = {"expense", "income", "refund", "adjustment"}
# Reject dates more than ~1 day in the future (typo guard; §14). Backdating ok.
_MAX_FUTURE_DAYS = 1


class QuickAddRequest(BaseModel):
    # Ignore any unknown/forbidden fields (e.g. a client-supplied user_id or the
    # not-yet-implemented merchant_input/merchant_id) — never trusted.
    model_config = ConfigDict(extra="ignore")

    # JSON number or decimal string; parsed via Decimal (app/money.py).
    amount: str | int | float | None = None
    transaction_type: str = "expense"
    occurred_on: str | None = None
    currency: str = "ILS"
    note: str | None = None
    # Optional explicit category (§8). Must be a visible consumer-layer category;
    # omitted/null -> uncategorized. merchant-driven suggestions are out of scope.
    category_id: str | None = None
    # Optional typed merchant text (§8). Normalized-exact match reuses an existing
    # merchant, else a new one is created for this user. The pre-resolved
    # `merchant_id` path (recent chips) is deferred -> still dropped by extra=ignore.
    merchant_input: str | None = None


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
         occurred_on, note, category_id, merchant_id, raw_merchant_input)
    VALUES
        (:user_id, :amount_minor, :currency, :transaction_type, 'manual',
         :occurred_on, :note, CAST(:category_id AS uuid),
         CAST(:merchant_id AS uuid), :raw_merchant_input)
    RETURNING id::text AS id, amount_minor, currency, transaction_type, source,
              merchant_id::text AS merchant_id, category_id::text AS category_id,
              note, occurred_on::text AS occurred_on, is_card_settlement,
              created_at, updated_at
    """
)


# Normalized-exact resolve, else create (MERCHANT_NORMALIZATION_SPEC §7 `none`).
# ON CONFLICT on the (user_id, normalized_merchant_name) unique key makes this
# race-safe and idempotent: a repeat input reuses the same row (bumping
# updated_at for recency) and keeps the FIRST display_name. No fuzzy, no
# cross-script merge — different scripts produce different keys by construction.
_MERCHANT_UPSERT = text(
    """
    INSERT INTO merchants (user_id, normalized_merchant_name, display_name)
    VALUES (:user_id, :normalized, :display_name)
    ON CONFLICT (user_id, normalized_merchant_name)
    DO UPDATE SET updated_at = now()
    RETURNING id::text AS id, display_name
    """
)


async def _resolve_or_create_merchant(
    session, raw: str, user_id: str
) -> tuple[str, str] | None:
    """Return (merchant_id, display_name) for typed text, or None if blank."""
    normalized = normalize_merchant_name(raw)
    if not normalized:  # whitespace/invisible-only -> treat as no merchant
        return None
    row = (
        await session.execute(
            _MERCHANT_UPSERT,
            {
                "user_id": user_id,  # server-resolved ONLY
                "normalized": normalized,
                "display_name": display_form(raw),
            },
        )
    ).mappings().one()
    return row["id"], row["display_name"]


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
    category_id = body.category_id  # validated below; None -> uncategorized
    category_key: str | None = None
    merchant_display_name: str | None = None
    category_suggestion: dict | None = None
    params = {
        "user_id": principal.user_id,  # server-resolved ONLY
        "amount_minor": amount_minor,
        "currency": currency,
        "transaction_type": ttype,
        "occurred_on": occurred_on,
        "note": body.note,
        "category_id": category_id,
        "merchant_id": None,
        "raw_merchant_input": None,
    }
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            # Validate the explicit category (visible consumer-layer) before the
            # insert; raises 422 validation_error which must NOT become 503.
            if category_id is not None:
                category_key = await _validate_category(
                    session, category_id, principal.user_id
                )
            # Resolve/create the merchant for the server-resolved principal, and
            # preserve the verbatim typed text as raw_merchant_input (audit; §4).
            if body.merchant_input is not None:
                resolved = await _resolve_or_create_merchant(
                    session, body.merchant_input, principal.user_id
                )
                if resolved is not None:
                    params["merchant_id"], merchant_display_name = resolved
                    params["raw_merchant_input"] = clean_raw(body.merchant_input)
            # Category suggestion (SUGGEST-ONLY, §9 / contract step 3): when a
            # merchant resolved and the client set no category, surface the rule
            # suggestion in the response — the saved row stays as sent (never
            # auto-applied).
            if params["merchant_id"] is not None and category_id is None:
                rules = await fetch_active_rules(session, principal.user_id)
                s_id, s_key, s_src = resolve_suggestion(
                    rules, normalize_merchant_name(body.merchant_input)
                )
                if s_id is not None:
                    category_suggestion = {
                        "category_id": s_id, "category_key": s_key, "source": s_src,
                    }
            row = (await session.execute(_INSERT_SQL, params)).mappings().one()
            await session.commit()
    except AppError:
        raise  # validation_error (bad category/amount) must surface as-is
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
        merchant_display_name=merchant_display_name,  # resolved/created merchant
        category_id=row["category_id"],
        category_key=category_key,  # joined display key for an explicit category
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

    return QuickAddResponse(transaction=txn, category_suggestion=category_suggestion)


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


# =========================================================================== #
# DELETE /transactions/{id} — hard delete, ownership-scoped (API_CONTRACT §9).
# =========================================================================== #

# Scoped to the resolved principal; RETURNING lets us tell "deleted" from
# "missing/not-owned" without a separate existence probe (no leak).
_DELETE_BY_ID = text(
    "DELETE FROM transactions WHERE id = :id AND user_id = :user_id "
    "RETURNING id::text AS id"
)


@router.delete(
    "/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_transaction(
    request: Request,
    transaction_id: str,
    principal: Principal = Depends(require_principal),
) -> Response:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # A non-UUID id cannot correspond to any row -> generic 404 (no leak).
    try:
        uuid.UUID(transaction_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            deleted = (
                await session.execute(
                    _DELETE_BY_ID,
                    {"id": transaction_id, "user_id": principal.user_id},
                )
            ).mappings().one_or_none()
            await session.commit()
    except Exception:
        log_event(
            "delete_transaction",
            request_id=request_id,
            endpoint="/api/v1/transactions/{id}",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    # Nothing deleted -> missing OR owned by another principal: identical 404.
    if deleted is None:
        raise AppError(code="not_found")

    # Privacy-safe log: ids/status only — never amount, note, or merchant text.
    log_event(
        "delete_transaction",
        request_id=request_id,
        endpoint="/api/v1/transactions/{id}",
        status=204,
        user_id=principal.user_id,
        transaction_id=deleted["id"],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================== #
# PATCH /transactions/{id} — partial edit, ownership-scoped (API_CONTRACT §9).
# =========================================================================== #

# Editable in THIS slice: amount, transaction_type, occurred_on, note,
# category_id (null clears). The contract's merchant_id/merchant_input require
# merchant resolution (a later slice) — dropped via extra="ignore", same as
# Quick Add, so a client sending them today is a no-op rather than an error.
_EDITABLE_FIELDS = {"amount", "transaction_type", "occurred_on", "note", "category_id"}

_SELECT_FOR_PATCH = text(
    "SELECT transaction_type, amount_minor FROM transactions "
    "WHERE id = :id AND user_id = :user_id"
)


class PatchRequest(BaseModel):
    # extra="ignore": unknown/forbidden fields (client user_id, merchant_*) are
    # never trusted. model_fields_set then tells provided-vs-omitted apart so a
    # `null` (clear) is distinct from an absent field (leave unchanged).
    model_config = ConfigDict(extra="ignore")

    amount: str | int | float | None = None
    transaction_type: str | None = None
    occurred_on: str | None = None
    note: str | None = None
    category_id: str | None = None


async def _validate_category(session, category_id: str, user_id: str) -> str:
    """Validate a category_id and return its display key (§8/§9).

    Must be a VISIBLE CONSUMER-LAYER category: visible = system (user_id IS NULL)
    or owned by the principal. A bank_movement category → `not_consumer_category`;
    unknown/non-visible → `invalid_category`. Both surface as 422
    validation_error (field code). Returns the category `key` on success.
    """
    try:
        uuid.UUID(category_id)
    except (ValueError, AttributeError, TypeError):
        raise _field_error("category_id", "invalid_category", "Unknown category.") from None
    row = (
        await session.execute(
            text(
                "SELECT layer, key AS category_key FROM categories "
                "WHERE id = CAST(:cid AS uuid) AND (user_id IS NULL OR user_id = :uid)"
            ),
            {"cid": category_id, "uid": user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise _field_error("category_id", "invalid_category", "Unknown category.")
    if row["layer"] != "consumer_spending":
        raise _field_error(
            "category_id", "not_consumer_category", "Choose a spending category."
        )
    return row["category_key"]


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
async def patch_transaction(
    request: Request,
    transaction_id: str,
    body: PatchRequest,
    principal: Principal = Depends(require_principal),
) -> TransactionOut:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # Malformed id -> generic 404 (no leak), identical to GET/DELETE.
    try:
        uuid.UUID(transaction_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    # PATCH semantics: only fields actually present in the body are applied.
    provided = body.model_fields_set & _EDITABLE_FIELDS
    if not provided:
        # "all optional; at least one required" (§9) -> 422 validation_error.
        raise AppError(
            code="validation_error",
            field_errors=[
                {"field": "body", "code": "empty_patch",
                 "message": "Provide at least one field to update."}
            ],
        )

    # --- DB-independent validation (nothing read/written yet) ---------------- #
    new_type: str | None = None
    if "transaction_type" in provided:
        new_type = body.transaction_type
        if new_type not in _VALID_TYPES:
            raise _field_error("transaction_type", "invalid_enum", "Invalid transaction type.")

    new_occurred_on: date | None = None
    if "occurred_on" in provided:
        if body.occurred_on is None:
            raise _field_error("occurred_on", "invalid_date", "Enter a valid date.")
        new_occurred_on = _resolve_occurred_on(body.occurred_on)

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            existing = (
                await session.execute(
                    _SELECT_FOR_PATCH,
                    {"id": transaction_id, "user_id": principal.user_id},
                )
            ).mappings().one_or_none()
            # Missing OR owned by another principal -> identical generic 404.
            if existing is None:
                raise AppError(code="not_found")

            if "category_id" in provided and body.category_id is not None:
                await _validate_category(session, body.category_id, principal.user_id)

            # --- compute changed columns (validation may raise 422) ---------- #
            updates: dict[str, object] = {}
            effective_type = new_type if new_type is not None else existing["transaction_type"]
            if "transaction_type" in provided:
                updates["transaction_type"] = new_type
            if "amount" in provided:
                # Re-normalize against the (possibly updated) type; raises 422.
                updates["amount_minor"] = parse_amount_to_minor(body.amount, effective_type)
            elif "transaction_type" in provided:
                # Type changed without a new amount: re-sign the existing
                # magnitude to the new type (§9). expense -> negative.
                magnitude = abs(existing["amount_minor"])
                updates["amount_minor"] = -magnitude if new_type == "expense" else magnitude
            if "occurred_on" in provided:
                updates["occurred_on"] = new_occurred_on
            if "note" in provided:
                updates["note"] = body.note  # may be None (clear the note)
            if "category_id" in provided:
                updates["category_id"] = body.category_id  # validated; None clears

            # --- build + run the UPDATE (column names are server-controlled) - #
            set_parts = ["updated_at = now()"]
            params: dict[str, object] = {"id": transaction_id, "user_id": principal.user_id}
            for col, val in updates.items():
                # uuid column needs an explicit cast for the asyncpg string bind.
                placeholder = "CAST(:category_id AS uuid)" if col == "category_id" else f":{col}"
                set_parts.append(f"{col} = {placeholder}")
                params[col] = val
            await session.execute(
                text(
                    f"UPDATE transactions SET {', '.join(set_parts)} "
                    "WHERE id = :id AND user_id = :user_id"
                ),
                params,
            )
            # Re-read through the shared projection so the response shape is
            # byte-identical to GET /transactions/{id} (joined category_key etc.).
            row = (
                await session.execute(
                    _SELECT_BY_ID,
                    {"id": transaction_id, "user_id": principal.user_id},
                )
            ).mappings().one()
            await session.commit()
    except AppError:
        raise  # 404 / validation_error must not be masked as 503
    except Exception:
        log_event(
            "patch_transaction",
            request_id=request_id,
            endpoint="/api/v1/transactions/{id}",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    txn = _row_to_transaction_out(row)
    # Privacy-safe log: ids/status only — never amount, note, or merchant text.
    log_event(
        "patch_transaction",
        request_id=request_id,
        endpoint="/api/v1/transactions/{id}",
        status=200,
        user_id=principal.user_id,
        transaction_id=txn.id,
    )
    return txn


# =========================================================================== #
# POST /transactions/{id}/categorize — set category + optional rule promotion
# (API_CONTRACT §10; CATEGORY_TAXONOMY §9; update-not-stack).
# =========================================================================== #

_MATCH_TYPES = {"merchant_exact", "merchant_contains"}
# Generic tokens too noisy to anchor a `contains` rule (MERCHANT_NORMALIZATION
# SPEC §10/§12). A contains match_value must also clear a minimum length.
_GENERIC_TOKENS = {
    "market", "cafe", "kiosk", "makolet", "paybox", "bit", "transfer", "atm",
    "other", "misc", "shop", "store",
}
_MIN_CONTAINS_LEN = 3

# Update-not-stack: one rule per (user_id, match_type, match_value). A repeat
# correction UPDATES category/source/updated_at on the single existing row.
_RULE_UPSERT = text(
    """
    INSERT INTO category_rules
        (user_id, match_type, match_value, category_id, source, priority, is_active)
    VALUES
        (:user_id, :match_type, :match_value, CAST(:category_id AS uuid),
         'user_correction', 100, true)
    ON CONFLICT (user_id, match_type, match_value)
    DO UPDATE SET category_id = EXCLUDED.category_id, source = 'user_correction',
                  is_active = true, updated_at = now()
    RETURNING id::text AS id, match_type, category_id::text AS category_id,
              source, priority, is_active, updated_at
    """
)


class CategorizeRequest(BaseModel):
    # extra="ignore": a forged user_id (or any unknown field) is never trusted.
    model_config = ConfigDict(extra="ignore")

    category_id: str  # required; consumer-layer (validated below)
    promote_to_rule: bool = False
    match_type: str = "merchant_exact"
    apply_to_existing: bool = False


class CategorizeResponse(BaseModel):
    transaction: TransactionOut
    rule: dict | None = None
    applied_to_existing_count: int = 0


@router.post("/transactions/{transaction_id}/categorize", response_model=CategorizeResponse)
async def categorize_transaction(
    request: Request,
    transaction_id: str,
    body: CategorizeRequest,
    principal: Principal = Depends(require_principal),
) -> CategorizeResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # Malformed id -> generic 404 (no leak), identical to GET/PATCH/DELETE.
    try:
        uuid.UUID(transaction_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    if body.promote_to_rule and body.match_type not in _MATCH_TYPES:
        raise _field_error("match_type", "invalid_enum", "Invalid match type.")

    rule_out: dict | None = None
    applied_count = 0
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            # Existence + ownership (missing/non-owned -> identical generic 404).
            target = (
                await session.execute(
                    text(
                        "SELECT merchant_id::text AS merchant_id FROM transactions "
                        "WHERE id = :id AND user_id = :user_id"
                    ),
                    {"id": transaction_id, "user_id": principal.user_id},
                )
            ).mappings().one_or_none()
            if target is None:
                raise AppError(code="not_found")

            # Category must be a visible consumer-layer category (raises 422).
            category_key = await _validate_category(
                session, body.category_id, principal.user_id
            )

            # Set the target transaction's category (only that field + updated_at).
            await session.execute(
                text(
                    "UPDATE transactions SET category_id = CAST(:cat AS uuid), "
                    "updated_at = now() WHERE id = :id AND user_id = :user_id"
                ),
                {"cat": body.category_id, "id": transaction_id, "user_id": principal.user_id},
            )

            # Optional rule promotion (user confirmation IS promote_to_rule:true).
            if body.promote_to_rule:
                merchant_id = target["merchant_id"]
                if merchant_id is None:
                    raise _field_error(
                        "promote_to_rule", "unknown_merchant",
                        "Add a merchant before saving a rule.",
                    )
                # match_value derives from the merchant's normalized name (the
                # only fragment this endpoint exposes); contains is additionally
                # guarded against generic/too-short tokens.
                match_value = (
                    await session.execute(
                        text(
                            "SELECT normalized_merchant_name FROM merchants "
                            "WHERE id = CAST(:mid AS uuid) AND user_id = :user_id"
                        ),
                        {"mid": merchant_id, "user_id": principal.user_id},
                    )
                ).scalar_one()
                if body.match_type == "merchant_contains" and (
                    len(match_value) < _MIN_CONTAINS_LEN or match_value in _GENERIC_TOKENS
                ):
                    raise _field_error(
                        "match_type", "generic_fragment",
                        "That merchant is too generic for a rule.",
                    )

                rule_row = (
                    await session.execute(
                        _RULE_UPSERT,
                        {
                            "user_id": principal.user_id,
                            "match_type": body.match_type,
                            "match_value": match_value,  # stored, NEVER echoed/logged
                            "category_id": body.category_id,
                        },
                    )
                ).mappings().one()
                rule_out = {
                    "id": rule_row["id"],
                    "match_type": rule_row["match_type"],
                    "match_value_present": True,  # raw fragment never returned
                    "category_id": rule_row["category_id"],
                    "category_key": category_key,
                    "source": rule_row["source"],
                    "priority": rule_row["priority"],
                    "is_active": rule_row["is_active"],
                    "updated_at": _rfc3339(rule_row["updated_at"]),
                }

                # Going-forward by default; bulk rewrite of history is opt-in and
                # scoped to the principal's OTHER transactions for this merchant.
                if body.apply_to_existing:
                    res = await session.execute(
                        text(
                            "UPDATE transactions SET category_id = CAST(:cat AS uuid), "
                            "updated_at = now() WHERE user_id = :user_id "
                            "AND merchant_id = CAST(:mid AS uuid) AND id <> :id"
                        ),
                        {
                            "cat": body.category_id,
                            "user_id": principal.user_id,
                            "mid": merchant_id,
                            "id": transaction_id,
                        },
                    )
                    applied_count = res.rowcount

            # Re-read the target through the shared projection (joined category_key).
            row = (
                await session.execute(
                    _SELECT_BY_ID,
                    {"id": transaction_id, "user_id": principal.user_id},
                )
            ).mappings().one()
            await session.commit()
    except AppError:
        raise  # 404 / validation_error must not be masked as 503
    except Exception:
        log_event(
            "categorize_transaction",
            request_id=request_id,
            endpoint="/api/v1/transactions/{id}/categorize",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    txn = _row_to_transaction_out(row)
    # Privacy-safe log: ids / enums / counts only — never category text, merchant
    # text, the normalized key, or the rule match_value.
    log_event(
        "categorize_transaction",
        request_id=request_id,
        endpoint="/api/v1/transactions/{id}/categorize",
        status=200,
        user_id=principal.user_id,
        transaction_id=txn.id,
        category_id=body.category_id,
        rule_id=rule_out["id"] if rule_out else None,
        match_type=body.match_type if rule_out else None,
        count=applied_count,
    )
    return CategorizeResponse(
        transaction=txn, rule=rule_out, applied_to_existing_count=applied_count
    )

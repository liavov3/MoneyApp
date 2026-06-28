"""/api/v1/recurring-templates — CRUD for recurring expense templates
(API_CONTRACT §12; DATABASE_SCHEMA §3.7/§9; RECURRING_COMMITMENTS_SPEC).

PROJECTION-ONLY: no endpoint here ever writes a `transactions` row. Templates
feed Home's "Upcoming commitments" / `committed_amount_minor` (§13) and are
NEVER blended into actual spend. Product/UI calls these "הוצאות קבועות"; the
backend/domain name stays `recurring_expense_templates` and the API path stays
`/recurring-templates` (no aliases).

Auth required; `user_id` is server-resolved ONLY (a client-supplied user_id is
ignored). Ownership mismatch / missing / malformed id → generic 404 `not_found`.
Money is signed agorot stored NEGATIVE (expense convention, §12); the API accepts
a non-negative magnitude. Privacy: name, note, amount, merchant text are NEVER
logged.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event
from app.money import parse_amount_to_minor
from app.routers.transactions import _field_error, _rfc3339, _validate_category

router = APIRouter()

_CADENCES = {"weekly", "monthly", "yearly"}
# The template amount is stored with the expense sign convention (§12); the API
# accepts a non-negative magnitude and the server owns the sign.
_TEMPLATE_SIGN_TYPE = "expense"


class TemplateOut(BaseModel):
    id: str
    name: str
    amount_minor: int
    currency: str
    category_id: str
    category_key: str | None
    merchant_id: str | None
    cadence: str
    next_expected_date: str
    counts_in_projection: bool
    is_active: bool
    note: str | None
    created_at: str
    updated_at: str


class TemplateListResponse(BaseModel):
    items: list[TemplateOut]


class CreateTemplateRequest(BaseModel):
    # Ignore unknown/forbidden fields (a client-supplied user_id/is_active is
    # never trusted; is_active defaults true on create per §12).
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    amount: str | int | float | None = None
    category_id: str | None = None
    merchant_id: str | None = None
    cadence: str = "monthly"
    next_expected_date: str | None = None
    counts_in_projection: bool = True
    note: str | None = None
    currency: str = "ILS"


class PatchTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    amount: str | int | float | None = None
    category_id: str | None = None
    merchant_id: str | None = None
    cadence: str | None = None
    next_expected_date: str | None = None
    counts_in_projection: bool | None = None
    is_active: bool | None = None
    note: str | None = None


# Shared projection + category-key join (create/list/read-back identical shape).
_TEMPLATE_SELECT = (
    "rt.id::text AS id, rt.name, rt.amount_minor, rt.currency, "
    "rt.category_id::text AS category_id, c.key AS category_key, "
    "rt.merchant_id::text AS merchant_id, rt.cadence, "
    "rt.next_expected_date::text AS next_expected_date, "
    "rt.counts_in_projection, rt.is_active, rt.note, "
    "rt.created_at, rt.updated_at "
    "FROM recurring_expense_templates rt "
    "LEFT JOIN categories c ON c.id = rt.category_id"
)


def _row_to_template_out(r) -> TemplateOut:
    return TemplateOut(
        id=r["id"],
        name=r["name"],
        amount_minor=r["amount_minor"],
        currency=r["currency"],
        category_id=r["category_id"],
        category_key=r["category_key"],
        merchant_id=r["merchant_id"],
        cadence=r["cadence"],
        next_expected_date=r["next_expected_date"],
        counts_in_projection=r["counts_in_projection"],
        is_active=r["is_active"],
        note=r["note"],
        created_at=_rfc3339(r["created_at"]),
        updated_at=_rfc3339(r["updated_at"]),
    )


def _parse_next_expected_date(raw: str | None) -> date:
    """Parse a required `YYYY-MM-DD`; raise 422 on a bad value.

    No future-date guard (unlike a transaction's occurred_on): a commitment's
    next charge is naturally in the future.
    """
    if raw is None:
        raise _field_error("next_expected_date", "invalid_date", "Enter a valid date.")
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        raise _field_error(
            "next_expected_date", "invalid_date", "Enter a valid date."
        ) from None


async def _validate_merchant(session, merchant_id: str, user_id: str) -> None:
    """A provided merchant must belong to the principal (avoids a raw FK 503)."""
    try:
        uuid.UUID(merchant_id)
    except (ValueError, AttributeError, TypeError):
        raise _field_error("merchant_id", "invalid_merchant", "Unknown merchant.") from None
    found = (
        await session.execute(
            text(
                "SELECT 1 FROM merchants WHERE id = CAST(:mid AS uuid) AND user_id = :uid"
            ),
            {"mid": merchant_id, "uid": user_id},
        )
    ).scalar_one_or_none()
    if found is None:
        raise _field_error("merchant_id", "invalid_merchant", "Unknown merchant.")


def _validate_currency(currency: str) -> None:
    if not isinstance(currency, str) or len(currency) != 3:
        raise _field_error("currency", "invalid_currency", "Invalid currency code.")


# =========================================================================== #
# POST /recurring-templates — create (API_CONTRACT §12). Writes NO transaction.
# =========================================================================== #
_INSERT_SQL = text(
    """
    INSERT INTO recurring_expense_templates
        (user_id, name, amount_minor, currency, category_id, merchant_id,
         cadence, next_expected_date, counts_in_projection, note)
    VALUES
        (:user_id, :name, :amount_minor, :currency, CAST(:category_id AS uuid),
         CAST(:merchant_id AS uuid), :cadence, :next_expected_date,
         :counts_in_projection, :note)
    RETURNING id::text AS id
    """
)


@router.post(
    "/recurring-templates",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    request: Request,
    body: CreateTemplateRequest,
    principal: Principal = Depends(require_principal),
) -> TemplateOut:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # --- DB-independent validation (nothing persisted on failure) ----------- #
    if not body.name or not body.name.strip():
        raise _field_error("name", "required", "Name is required.")
    if body.cadence not in _CADENCES:
        raise _field_error("cadence", "invalid_enum", "Invalid cadence.")
    _validate_currency(body.currency)
    next_date = _parse_next_expected_date(body.next_expected_date)
    # Positive magnitude in -> stored NEGATIVE (expense convention, §12).
    amount_minor = parse_amount_to_minor(body.amount, _TEMPLATE_SIGN_TYPE)
    if body.category_id is None:
        raise _field_error("category_id", "required", "Category is required.")

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            # Consumer-layer category (raises 422; bank_movement -> not_consumer).
            await _validate_category(session, body.category_id, principal.user_id)
            if body.merchant_id is not None:
                await _validate_merchant(session, body.merchant_id, principal.user_id)

            new_id = (
                await session.execute(
                    _INSERT_SQL,
                    {
                        "user_id": principal.user_id,  # server-resolved ONLY
                        "name": body.name.strip(),
                        "amount_minor": amount_minor,
                        "currency": body.currency,
                        "category_id": body.category_id,
                        "merchant_id": body.merchant_id,
                        "cadence": body.cadence,
                        "next_expected_date": next_date,
                        "counts_in_projection": body.counts_in_projection,
                        "note": body.note,
                    },
                )
            ).scalar_one()
            row = (
                await session.execute(
                    text(f"SELECT {_TEMPLATE_SELECT} WHERE rt.id = CAST(:id AS uuid)"),
                    {"id": new_id},
                )
            ).mappings().one()
            await session.commit()
    except AppError:
        raise  # validation_error must surface as-is, not 503
    except Exception:
        log_event(
            "create_template",
            request_id=request_id,
            endpoint="/api/v1/recurring-templates",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    tpl = _row_to_template_out(row)
    # Privacy-safe log: ids/enums only — never name, note, amount, merchant text.
    log_event(
        "create_template",
        request_id=request_id,
        endpoint="/api/v1/recurring-templates",
        status=201,
        user_id=principal.user_id,
        template_id=tpl.id,
        category_id=tpl.category_id,
        cadence=tpl.cadence,
    )
    return tpl


# =========================================================================== #
# GET /recurring-templates?active=<bool> — list, principal-scoped (§12).
# =========================================================================== #
@router.get("/recurring-templates", response_model=TemplateListResponse)
async def list_templates(
    request: Request,
    principal: Principal = Depends(require_principal),
    active: bool | None = Query(default=None),
) -> TemplateListResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")

    where = ["rt.user_id = :user_id"]
    params: dict = {"user_id": principal.user_id}
    if active is not None:
        where.append("rt.is_active = :active")
        params["active"] = active

    # Deterministic order (contract is silent): soonest charge first, id tiebreak
    # — consistent with Home's upcoming_commitments ordering.
    sql = text(
        f"SELECT {_TEMPLATE_SELECT} WHERE {' AND '.join(where)} "
        "ORDER BY rt.next_expected_date ASC, rt.id ASC"
    )

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (await session.execute(sql, params)).mappings().all()
    except Exception:
        log_event(
            "list_templates",
            request_id=request_id,
            endpoint="/api/v1/recurring-templates",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    items = [_row_to_template_out(r) for r in rows]
    log_event(
        "list_templates",
        request_id=request_id,
        endpoint="/api/v1/recurring-templates",
        status=200,
        user_id=principal.user_id,
        row_count=len(items),
    )
    return TemplateListResponse(items=items)


# =========================================================================== #
# PATCH /recurring-templates/{id} — partial edit, ownership-scoped (§12).
# =========================================================================== #
_PATCHABLE = {
    "name", "amount", "category_id", "merchant_id", "cadence",
    "next_expected_date", "counts_in_projection", "is_active", "note",
}


@router.patch("/recurring-templates/{template_id}", response_model=TemplateOut)
async def patch_template(
    request: Request,
    template_id: str,
    body: PatchTemplateRequest,
    principal: Principal = Depends(require_principal),
) -> TemplateOut:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # Malformed id -> generic 404 (no leak), identical to transactions.
    try:
        uuid.UUID(template_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    provided = body.model_fields_set & _PATCHABLE
    if not provided:
        raise AppError(
            code="validation_error",
            field_errors=[{
                "field": "body", "code": "empty_patch",
                "message": "Provide at least one field to update.",
            }],
        )

    # --- DB-independent validation ------------------------------------------ #
    updates: dict[str, object] = {}
    if "name" in provided:
        if not body.name or not body.name.strip():
            raise _field_error("name", "required", "Name is required.")
        updates["name"] = body.name.strip()
    if "cadence" in provided:
        if body.cadence not in _CADENCES:
            raise _field_error("cadence", "invalid_enum", "Invalid cadence.")
        updates["cadence"] = body.cadence
    if "next_expected_date" in provided:
        updates["next_expected_date"] = _parse_next_expected_date(body.next_expected_date)
    if "amount" in provided:
        updates["amount_minor"] = parse_amount_to_minor(body.amount, _TEMPLATE_SIGN_TYPE)
    if "counts_in_projection" in provided:
        if body.counts_in_projection is None:
            raise _field_error("counts_in_projection", "invalid", "Must be true or false.")
        updates["counts_in_projection"] = body.counts_in_projection
    if "is_active" in provided:
        if body.is_active is None:
            raise _field_error("is_active", "invalid", "Must be true or false.")
        updates["is_active"] = body.is_active
    if "note" in provided:
        updates["note"] = body.note  # may be None (clear)

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            # Existence + ownership (missing/non-owned -> identical generic 404).
            exists = (
                await session.execute(
                    text(
                        "SELECT 1 FROM recurring_expense_templates "
                        "WHERE id = :id AND user_id = :user_id"
                    ),
                    {"id": template_id, "user_id": principal.user_id},
                )
            ).scalar_one_or_none()
            if exists is None:
                raise AppError(code="not_found")

            if "category_id" in provided:
                if body.category_id is None:  # NOT NULL column; cannot clear
                    raise _field_error("category_id", "required", "Category is required.")
                await _validate_category(session, body.category_id, principal.user_id)
                updates["category_id"] = body.category_id
            if "merchant_id" in provided and body.merchant_id is not None:
                await _validate_merchant(session, body.merchant_id, principal.user_id)
                updates["merchant_id"] = body.merchant_id
            elif "merchant_id" in provided:  # explicit null -> clear the link
                updates["merchant_id"] = None

            # --- build UPDATE (column names server-controlled) -------------- #
            set_parts = ["updated_at = now()"]
            params: dict[str, object] = {"id": template_id, "user_id": principal.user_id}
            for col, val in updates.items():
                if col in ("category_id", "merchant_id"):
                    placeholder = f"CAST(:{col} AS uuid)"
                else:
                    placeholder = f":{col}"
                set_parts.append(f"{col} = {placeholder}")
                params[col] = val
            await session.execute(
                text(
                    "UPDATE recurring_expense_templates "
                    f"SET {', '.join(set_parts)} WHERE id = :id AND user_id = :user_id"
                ),
                params,
            )
            row = (
                await session.execute(
                    text(f"SELECT {_TEMPLATE_SELECT} WHERE rt.id = CAST(:id AS uuid)"),
                    {"id": template_id},
                )
            ).mappings().one()
            await session.commit()
    except AppError:
        raise
    except Exception:
        log_event(
            "patch_template",
            request_id=request_id,
            endpoint="/api/v1/recurring-templates/{id}",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    tpl = _row_to_template_out(row)
    log_event(
        "patch_template",
        request_id=request_id,
        endpoint="/api/v1/recurring-templates/{id}",
        status=200,
        user_id=principal.user_id,
        template_id=tpl.id,
        category_id=tpl.category_id,
        cadence=tpl.cadence,
    )
    return tpl


# =========================================================================== #
# DELETE /recurring-templates/{id} — hard delete, 204, ownership-scoped (§12).
# Deactivate (keep history) is the PATCH {is_active:false} path; DELETE removes
# a template created in error. Never touches `transactions`.
# =========================================================================== #
_DELETE_SQL = text(
    "DELETE FROM recurring_expense_templates "
    "WHERE id = :id AND user_id = :user_id RETURNING id::text AS id"
)


@router.delete(
    "/recurring-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_template(
    request: Request,
    template_id: str,
    principal: Principal = Depends(require_principal),
) -> Response:
    request_id = getattr(request.state, "request_id", "req_unknown")

    try:
        uuid.UUID(template_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            deleted = (
                await session.execute(
                    _DELETE_SQL,
                    {"id": template_id, "user_id": principal.user_id},
                )
            ).mappings().one_or_none()
            await session.commit()
    except Exception:
        log_event(
            "delete_template",
            request_id=request_id,
            endpoint="/api/v1/recurring-templates/{id}",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    if deleted is None:  # missing OR non-owned -> identical generic 404
        raise AppError(code="not_found")

    log_event(
        "delete_template",
        request_id=request_id,
        endpoint="/api/v1/recurring-templates/{id}",
        status=204,
        user_id=principal.user_id,
        template_id=deleted["id"],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

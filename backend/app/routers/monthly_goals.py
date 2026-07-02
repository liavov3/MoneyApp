"""/api/v1/monthly-goals — per-user goals for expense / income / savings.

Additive feature OUTSIDE the frozen v0.0.1 contract; only the mobile app
consumes it, so the shapes are free to evolve. Each goal is a positive
integer-agorot cap (never signed — a goal is a target, not an expense). A goal
has a `goal_type` ('expense'|'income'|'savings') and a `scope`:
  - 'default'        : the standing goal for that type (month IS NULL)
  - 'month_override' : a one-month override for a specific 'YYYY-MM'

GET returns the EFFECTIVE state (override wins over default) for all three types
for a given month. PUT upserts one goal. DELETE removes one (idempotent — used
to drop an override and fall back to the default).

Auth required; `user_id` is server-resolved ONLY — a client-supplied user_id is
ignored (extra="ignore"). Privacy: amounts are NEVER logged; logs carry
ids/goal_type/scope/month/status only.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event
from app.routers.transactions import _field_error, _month_bounds

router = APIRouter()

_GOAL_TYPES = ("expense", "income", "savings")  # canonical order for GET items
_GOAL_TYPE_SET = set(_GOAL_TYPES)
_SCOPES = {"default", "month_override"}


# --------------------------------------------------------------------------- #
# Response / request models
# --------------------------------------------------------------------------- #
class GoalTypeState(BaseModel):
    goal_type: str
    default_amount_minor: int | None
    override_amount_minor: int | None
    effective_amount_minor: int | None
    effective_source: str | None  # 'month_override' | 'default' | None


class MonthlyGoalsResponse(BaseModel):
    month: str
    currency: str
    items: list[GoalTypeState]  # always 3, ordered expense, income, savings


class SavedGoal(BaseModel):
    goal_type: str
    scope: str
    month: str | None
    amount_minor: int
    currency: str


class PutGoalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # ignore any client-sent user_id

    goal_type: str | None = None
    scope: str | None = None
    month: str | None = None
    amount_minor: int | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _base_currency(session, user_id: str) -> str:
    return (
        await session.execute(
            text("SELECT base_currency FROM users WHERE id = :u"),
            {"u": user_id},
        )
    ).scalar_one_or_none() or "ILS"


def _validate_goal_type(value: str | None) -> str:
    if value not in _GOAL_TYPE_SET:
        raise _field_error(
            "goal_type", "invalid_enum", "Must be expense, income, or savings."
        )
    return value


def _validate_scope(value: str | None) -> str:
    if value not in _SCOPES:
        raise _field_error(
            "scope", "invalid_enum", "Must be default or month_override."
        )
    return value


def _validate_amount(value: object) -> int:
    # A goal is a positive integer-agorot cap. Reject None/bool/non-int/<=0.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _field_error(
            "amount_minor",
            "invalid_amount",
            "Amount must be a positive integer (agorot).",
        )
    return value


# --------------------------------------------------------------------------- #
# GET /monthly-goals?month=YYYY-MM  (default = server current month)
# --------------------------------------------------------------------------- #
@router.get("/monthly-goals", response_model=MonthlyGoalsResponse)
async def get_monthly_goals(
    request: Request,
    principal: Principal = Depends(require_principal),
    month: str | None = Query(default=None),
) -> MonthlyGoalsResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")

    month_str = month if month is not None else date.today().strftime("%Y-%m")
    _month_bounds(month_str)  # validation only; raises 422 invalid_month

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT goal_type, scope, amount_minor, currency "
                        "FROM monthly_goals "
                        "WHERE user_id = :u AND ("
                        "  scope = 'default' "
                        "  OR (scope = 'month_override' AND month = :m)"
                        ")"
                    ),
                    {"u": principal.user_id, "m": month_str},
                )
            ).mappings().all()
            base_currency = await _base_currency(session, principal.user_id)
    except AppError:
        raise
    except Exception:
        log_event(
            "get_monthly_goals",
            request_id=request_id,
            endpoint="/api/v1/monthly-goals",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    defaults: dict[str, int] = {}
    overrides: dict[str, int] = {}
    currency = base_currency
    for r in rows:
        currency = r["currency"]  # any row's currency wins over the base default
        if r["scope"] == "default":
            defaults[r["goal_type"]] = r["amount_minor"]
        else:
            overrides[r["goal_type"]] = r["amount_minor"]

    items: list[GoalTypeState] = []
    for gt in _GOAL_TYPES:
        d = defaults.get(gt)
        o = overrides.get(gt)
        if o is not None:
            eff, src = o, "month_override"
        elif d is not None:
            eff, src = d, "default"
        else:
            eff, src = None, None
        items.append(
            GoalTypeState(
                goal_type=gt,
                default_amount_minor=d,
                override_amount_minor=o,
                effective_amount_minor=eff,
                effective_source=src,
            )
        )

    log_event(
        "get_monthly_goals",
        request_id=request_id,
        endpoint="/api/v1/monthly-goals",
        status=200,
        user_id=principal.user_id,
        month=month_str,
    )
    return MonthlyGoalsResponse(month=month_str, currency=currency, items=items)


# --------------------------------------------------------------------------- #
# PUT /monthly-goals  (body upsert)
# --------------------------------------------------------------------------- #
_UPSERT_DEFAULT_SQL = text(
    """
    INSERT INTO monthly_goals
        (user_id, goal_type, scope, month, amount_minor, currency)
    VALUES (:u, :gt, 'default', NULL, :amt, :cur)
    ON CONFLICT (user_id, goal_type) WHERE scope = 'default'
    DO UPDATE SET amount_minor = EXCLUDED.amount_minor,
                  currency = EXCLUDED.currency,
                  updated_at = now()
    RETURNING goal_type, scope, month, amount_minor, currency
    """
)

_UPSERT_OVERRIDE_SQL = text(
    """
    INSERT INTO monthly_goals
        (user_id, goal_type, scope, month, amount_minor, currency)
    VALUES (:u, :gt, 'month_override', :month, :amt, :cur)
    ON CONFLICT (user_id, goal_type, month) WHERE scope = 'month_override'
    DO UPDATE SET amount_minor = EXCLUDED.amount_minor,
                  currency = EXCLUDED.currency,
                  updated_at = now()
    RETURNING goal_type, scope, month, amount_minor, currency
    """
)


@router.put(
    "/monthly-goals",
    response_model=SavedGoal,
    status_code=status.HTTP_200_OK,
)
async def put_monthly_goal(
    request: Request,
    body: PutGoalRequest,
    principal: Principal = Depends(require_principal),
) -> SavedGoal:
    request_id = getattr(request.state, "request_id", "req_unknown")

    goal_type = _validate_goal_type(body.goal_type)
    scope = _validate_scope(body.scope)
    amount = _validate_amount(body.amount_minor)

    if scope == "month_override":
        if body.month is None:
            raise _field_error("month", "required", "Month is required.")
        _month_bounds(body.month)  # raises 422 invalid_month
        month_val: str | None = body.month
        sql = _UPSERT_OVERRIDE_SQL
    else:  # default -> month is always NULL (ignore any provided)
        month_val = None
        sql = _UPSERT_DEFAULT_SQL

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            currency = await _base_currency(session, principal.user_id)
            params = {
                "u": principal.user_id,  # server-resolved ONLY
                "gt": goal_type,
                "amt": amount,
                "cur": currency,
            }
            if scope == "month_override":
                params["month"] = month_val
            row = (await session.execute(sql, params)).mappings().one()
            await session.commit()
    except AppError:
        raise
    except Exception:
        log_event(
            "put_monthly_goal",
            request_id=request_id,
            endpoint="/api/v1/monthly-goals",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    log_event(
        "put_monthly_goal",
        request_id=request_id,
        endpoint="/api/v1/monthly-goals",
        status=200,
        user_id=principal.user_id,
        goal_type=row["goal_type"],
        scope=row["scope"],
        month=row["month"],
    )
    return SavedGoal(
        goal_type=row["goal_type"],
        scope=row["scope"],
        month=row["month"],
        amount_minor=row["amount_minor"],
        currency=row["currency"],
    )


# --------------------------------------------------------------------------- #
# DELETE /monthly-goals?goal_type=&scope=&month=  -> 204 (idempotent)
# --------------------------------------------------------------------------- #
@router.delete("/monthly-goals", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monthly_goal(
    request: Request,
    principal: Principal = Depends(require_principal),
    goal_type: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    month: str | None = Query(default=None),
) -> Response:
    request_id = getattr(request.state, "request_id", "req_unknown")

    gt = _validate_goal_type(goal_type)
    sc = _validate_scope(scope)

    if sc == "month_override":
        if month is None:
            raise _field_error("month", "required", "Month is required.")
        _month_bounds(month)
        where = "scope = 'month_override' AND month = :m"
        params = {"u": principal.user_id, "gt": gt, "m": month}
    else:
        where = "scope = 'default' AND month IS NULL"
        params = {"u": principal.user_id, "gt": gt}

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "DELETE FROM monthly_goals "
                    "WHERE user_id = :u AND goal_type = :gt AND " + where
                ),
                params,
            )
            await session.commit()
    except AppError:
        raise
    except Exception:
        log_event(
            "delete_monthly_goal",
            request_id=request_id,
            endpoint="/api/v1/monthly-goals",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    log_event(
        "delete_monthly_goal",
        request_id=request_id,
        endpoint="/api/v1/monthly-goals",
        status=204,
        user_id=principal.user_id,
        goal_type=gt,
        scope=sc,
        month=month,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

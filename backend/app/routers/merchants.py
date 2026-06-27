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

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import Principal, require_principal
from app.db import get_sessionmaker
from app.errors import AppError
from app.logging_utils import log_event
from app.merchants import display_form, normalize_merchant_name

router = APIRouter()

_DEFAULT_LIMIT = 8
_MAX_LIMIT = 20


def _field_error(field: str, code: str, message: str) -> AppError:
    return AppError(
        code="validation_error",
        field_errors=[{"field": field, "code": code, "message": message}],
    )


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


# All of the principal's merchants (+ stored default-category suggestion) for the
# in-process confidence match. Same projection as recent, minus the LIMIT.
_SELECT_FOR_MATCH = text(
    """
    SELECT m.id::text AS merchant_id, m.display_name, m.normalized_merchant_name,
           m.default_category_id::text AS suggested_category_id,
           c.key AS suggested_category_key,
           m.updated_at
    FROM merchants m
    LEFT JOIN categories c ON c.id = m.default_category_id
    WHERE m.user_id = :user_id
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


# =========================================================================== #
# GET /merchants/suggestions?query= — typed autocomplete + resolution (§ contract).
# =========================================================================== #

# Deterministic same-script ladder strength (MERCHANT_NORMALIZATION_SPEC §7).
# alias_exact / cross-script / fuzzy are deferred (no aliases or transliteration
# in this slice) and so never resolve — they fall through to `none`.
_CONFIDENCE_RANK = {
    "exact": 5,
    "normalized_exact": 4,
    "recent_suggestion": 3,
    "contains": 2,
    "none": 0,
}
# Only these deterministic same-script identities may auto-select (§7).
_AUTO_SELECT = {"exact", "normalized_exact"}


class SuggestionItemOut(BaseModel):
    merchant_id: str
    display_name: str
    confidence: str
    requires_confirmation: bool
    matched_via: str
    suggested_category_id: str | None
    suggested_category_key: str | None
    suggested_category_source: str


class SuggestionsResponse(BaseModel):
    query_confidence: str
    auto_select_merchant_id: str | None
    items: list[SuggestionItemOut]


def _match_confidence(nq: str, display_q: str, nm: str, display_m: str) -> str | None:
    """Confidence for the query vs one merchant, or None (no match) — §7.

    Same-script, alias-free, deterministic. Cross-script (different normalized
    key by construction) and typos fall through to None — never a fuzzy or
    transliteration merge (spec §5/§12).
    """
    if nq == nm:
        # Same normalized key + same script. Identical display => `exact`,
        # else only case/whitespace differed => `normalized_exact`.
        return "exact" if display_q == display_m else "normalized_exact"
    if nm.startswith(nq):
        # Merchant key begins with the typed fragment -> autocomplete.
        return "recent_suggestion"
    nq_tokens, nm_tokens = set(nq.split()), set(nm.split())
    if nq_tokens < nm_tokens or nm_tokens < nq_tokens:
        # Whole-token containment either way (e.g. "wolt tel aviv" vs "wolt").
        return "contains"
    return None


@router.get("/merchants/suggestions", response_model=SuggestionsResponse)
async def merchant_suggestions(
    request: Request,
    principal: Principal = Depends(require_principal),
    query: str = Query(...),
    limit: int = Query(default=_DEFAULT_LIMIT),
) -> SuggestionsResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    page_limit = max(1, min(int(limit), _MAX_LIMIT))

    nq = normalize_merchant_name(query)
    if not nq:  # empty/whitespace-only query -> 422 (contract: empty query)
        raise AppError(
            code="validation_error",
            field_errors=[
                {"field": "query", "code": "empty_query",
                 "message": "Enter a merchant to search."}
            ],
        )
    display_q = display_form(query)

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (
                await session.execute(
                    _SELECT_FOR_MATCH, {"user_id": principal.user_id}
                )
            ).mappings().all()
    except Exception:
        log_event(
            "merchant_suggestions",
            request_id=request_id,
            endpoint="/api/v1/merchants/suggestions",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    # ponytail: match the user's full merchant set in Python — fine for a
    # single-user manual MVP. Push prefix/exact filters into SQL if it grows.
    ranked: list[tuple[dict, str]] = []
    for r in rows:
        level = _match_confidence(
            nq, display_q, r["normalized_merchant_name"], r["display_name"]
        )
        if level is not None:
            ranked.append((r, level))

    # Strongest first, then most-recently-used (deterministic).
    ranked.sort(key=lambda rl: (_CONFIDENCE_RANK[rl[1]], rl[0]["updated_at"]), reverse=True)

    query_confidence = ranked[0][1] if ranked else "none"
    auto_select_merchant_id = next(
        (r["merchant_id"] for r, lvl in ranked if lvl in _AUTO_SELECT), None
    )

    items = [
        SuggestionItemOut(
            merchant_id=r["merchant_id"],
            display_name=r["display_name"],
            confidence=lvl,
            requires_confirmation=(lvl == "contains"),  # never auto-merge a contains
            matched_via="merchant",  # no aliases in this slice
            suggested_category_id=r["suggested_category_id"],
            suggested_category_key=r["suggested_category_key"],
            suggested_category_source=(
                "merchant_default" if r["suggested_category_id"] else "none"
            ),
        )
        for r, lvl in ranked[:page_limit]
    ]

    # Privacy-safe log: confidence enum + count only — never query or display_name.
    log_event(
        "merchant_suggestions",
        request_id=request_id,
        endpoint="/api/v1/merchants/suggestions",
        status=200,
        user_id=principal.user_id,
        confidence_level=query_confidence,
        row_count=len(items),
    )
    return SuggestionsResponse(
        query_confidence=query_confidence,
        auto_select_merchant_id=auto_select_merchant_id,
        items=items,
    )


# =========================================================================== #
# POST /merchants/{id}/aliases — user-confirmed alias / "Same as Golda?" (§11).
# =========================================================================== #

_SELECT_MERCHANT_OWNED = text(
    "SELECT id FROM merchants WHERE id = CAST(:mid AS uuid) AND user_id = :user_id"
)
_SELECT_ALIAS_BY_KEY = text(
    "SELECT id::text AS id, merchant_id::text AS merchant_id, source, confidence, "
    "created_at, last_seen_at FROM merchant_aliases "
    "WHERE user_id = :user_id AND normalized_alias_key = :nk"
)
_INSERT_ALIAS = text(
    """
    INSERT INTO merchant_aliases
        (user_id, merchant_id, alias_text, normalized_alias_key, source, confidence)
    VALUES
        (:user_id, CAST(:mid AS uuid), :alias_text, :nk, 'user_confirmed', 'user_confirmed')
    RETURNING id::text AS id, merchant_id::text AS merchant_id, source, confidence,
              created_at, last_seen_at
    """
)
_REPOINT_TXNS = text(
    "UPDATE transactions SET merchant_id = CAST(:mid AS uuid) "
    "WHERE merchant_id = CAST(:absorb AS uuid) AND user_id = :user_id"
)
_DELETE_MERCHANT = text(
    "DELETE FROM merchants WHERE id = CAST(:absorb AS uuid) AND user_id = :user_id"
)


class AliasCreateRequest(BaseModel):
    # extra="ignore": a forged user_id (or any unknown field) is never trusted.
    model_config = ConfigDict(extra="ignore")

    alias_text: str  # required; verbatim variant form (sensitive, never logged)
    absorb_merchant_id: str | None = None


@router.post("/merchants/{merchant_id}/aliases", status_code=status.HTTP_201_CREATED)
async def create_alias(
    request: Request,
    merchant_id: str,
    body: AliasCreateRequest,
    principal: Principal = Depends(require_principal),
) -> dict:
    request_id = getattr(request.state, "request_id", "req_unknown")

    # Malformed {id} -> generic 404 (no leak), same as the other resources.
    try:
        uuid.UUID(merchant_id)
    except (ValueError, AttributeError, TypeError):
        raise AppError(code="not_found") from None

    # Normalize the variant; an empty key is not a valid alias.
    nk = normalize_merchant_name(body.alias_text)
    if not nk:
        raise _field_error("alias_text", "empty_alias", "Enter a merchant name.")

    absorb = body.absorb_merchant_id
    if absorb is not None and absorb == merchant_id:
        raise _field_error(
            "absorb_merchant_id", "invalid_absorb", "Cannot absorb a merchant into itself."
        )

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            # Ownership of {id} (missing/not-owned -> identical generic 404).
            owned = (
                await session.execute(
                    _SELECT_MERCHANT_OWNED,
                    {"mid": merchant_id, "user_id": principal.user_id},
                )
            ).first()
            if owned is None:
                raise AppError(code="not_found")

            # absorb target must be a DIFFERENT merchant owned by the principal.
            if absorb is not None:
                try:
                    uuid.UUID(absorb)
                except (ValueError, AttributeError, TypeError):
                    raise _field_error(
                        "absorb_merchant_id", "unknown_merchant", "Unknown merchant."
                    ) from None
                absorb_owned = (
                    await session.execute(
                        _SELECT_MERCHANT_OWNED,
                        {"mid": absorb, "user_id": principal.user_id},
                    )
                ).first()
                if absorb_owned is None:
                    raise _field_error(
                        "absorb_merchant_id", "unknown_merchant", "Unknown merchant."
                    )

            # Alias-key uniqueness (UNIQUE(user_id, normalized_alias_key)): the key
            # resolves to exactly one merchant. Same merchant -> idempotent; a
            # DIFFERENT merchant -> 409 (the client must pick the canonical one).
            existing = (
                await session.execute(
                    _SELECT_ALIAS_BY_KEY, {"user_id": principal.user_id, "nk": nk}
                )
            ).mappings().one_or_none()
            if existing is not None:
                if existing["merchant_id"] != merchant_id:
                    raise AppError(code="conflict")
                alias_row = existing  # already points here -> idempotent
            else:
                alias_row = (
                    await session.execute(
                        _INSERT_ALIAS,
                        {
                            "user_id": principal.user_id,
                            "mid": merchant_id,
                            "alias_text": body.alias_text,  # stored, never logged
                            "nk": nk,
                        },
                    )
                ).mappings().one()

            # Absorb a duplicate merchant: re-point its transactions to {id}, then
            # drop it (cascade removes any of its own aliases — acceptable here,
            # an absorbed merchant is typically a fresh Quick Add duplicate).
            absorbed_count: int | None = None
            if absorb is not None:
                res = await session.execute(
                    _REPOINT_TXNS,
                    {"mid": merchant_id, "absorb": absorb, "user_id": principal.user_id},
                )
                absorbed_count = res.rowcount
                await session.execute(
                    _DELETE_MERCHANT, {"absorb": absorb, "user_id": principal.user_id}
                )

            await session.commit()
    except AppError:
        raise  # 404 / 409 / validation_error must surface as-is, never 503
    except Exception:
        log_event(
            "create_alias",
            request_id=request_id,
            endpoint="/api/v1/merchants/{id}/aliases",
            status=503,
        )
        raise AppError(code="backend_unavailable") from None

    last_seen = alias_row["last_seen_at"]
    result: dict = {
        "alias": {
            "id": alias_row["id"],
            "merchant_id": alias_row["merchant_id"],
            "source": alias_row["source"],
            "confidence": alias_row["confidence"],
            "created_at": _rfc3339(alias_row["created_at"]),
            "last_seen_at": _rfc3339(last_seen) if last_seen else None,
        }
    }
    # Present ONLY when a merchant was absorbed (contract §11).
    if absorb is not None:
        result["absorbed_merchant_id"] = absorb
        result["repointed_transaction_count"] = absorbed_count

    # Privacy-safe log: ids/counts only — never alias_text or the normalized key.
    log_event(
        "create_alias",
        request_id=request_id,
        endpoint="/api/v1/merchants/{id}/aliases",
        status=201,
        user_id=principal.user_id,
        merchant_id=merchant_id,
        alias_id=result["alias"]["id"],
        count=absorbed_count if absorb is not None else 0,
    )
    return result

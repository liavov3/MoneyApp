"""Category-rule suggestion resolution (CATEGORY_TAXONOMY §9 / MERCHANT_NORM §9).

Consumes the category_rules a user has confirmed (via the categorize endpoint)
and resolves the suggested category for a merchant, honoring the §9 precedence
ladder, highest first:

    user_correction merchant_exact
  > user_correction merchant_contains
  > system          merchant_exact
  > system          merchant_contains
  > recent-merchant memory (the category last used for this merchant)
  > merchant default (`merchants.default_category_id`)
  > none

Inactive rules are excluded (the SELECT filters `is_active`); everything is
user_id-scoped by the caller's query, so one user's rules never reach another.
Recent-memory only considers consumer-layer categories — bank_movement is never
suggested in Quick Add (§9). The raw `match_value` is consumed ONLY for matching
here — never returned to the client or logged (sensitive merchant text; §15).
"""

from __future__ import annotations

from sqlalchemy import text

# Active rules for one user, joined to the category key. user_id-scoped by bind.
RULES_SELECT = text(
    """
    SELECT cr.match_type, cr.match_value, cr.source, cr.updated_at,
           cr.category_id::text AS category_id, c.key AS category_key
    FROM category_rules cr
    JOIN categories c ON c.id = cr.category_id
    WHERE cr.user_id = :user_id AND cr.is_active = true
    """
)


async def fetch_active_rules(session, user_id: str) -> list[dict]:
    """Load the principal's active rules once; resolve many merchants in process."""
    rows = (await session.execute(RULES_SELECT, {"user_id": user_id})).mappings().all()
    return [dict(r) for r in rows]


# Most-recently-used CONSUMER category per merchant (§9 level 5). Recency leads:
# occurred_on then created_at. Only consumer_spending — bank_movement is never a
# Quick Add suggestion (§9). user_id-scoped by bind.
# ponytail: scans the user's categorized rows — fine for a single-user MVP; add a
# (user_id, merchant_id, occurred_on) index if it grows.
_RECENT_MEMORY_SELECT = text(
    """
    SELECT DISTINCT ON (t.merchant_id)
           t.merchant_id::text AS merchant_id,
           t.category_id::text AS category_id,
           c.key AS category_key
    FROM transactions t
    JOIN categories c ON c.id = t.category_id
    WHERE t.user_id = :user_id AND t.merchant_id IS NOT NULL
      AND c.layer = 'consumer_spending'
    ORDER BY t.merchant_id, t.occurred_on DESC, t.created_at DESC
    """
)


async def fetch_recent_memory(session, user_id: str) -> dict[str, tuple[str, str]]:
    """{merchant_id: (category_id, category_key)} — last consumer category used."""
    rows = (
        await session.execute(_RECENT_MEMORY_SELECT, {"user_id": user_id})
    ).mappings().all()
    return {r["merchant_id"]: (r["category_id"], r["category_key"]) for r in rows}


def _rule_matches(rule: dict, normalized_name: str) -> bool:
    if rule["match_type"] == "merchant_exact":
        return rule["match_value"] == normalized_name
    # merchant_contains: the fragment appears in the merchant's normalized name
    # (e.g. "wolt" in "wolt tel aviv"). Deterministic substring — never fuzzy.
    return rule["match_value"] in normalized_name


def resolve_suggestion(
    rules: list[dict],
    normalized_name: str,
    *,
    memory: tuple[str, str] | None = None,
    default: tuple[str, str] | None = None,
) -> tuple[str | None, str | None, str]:
    """Return (category_id, category_key, source) for one merchant via §9.

    `memory`/`default` are this merchant's (category_id, category_key) for the
    recent-memory and merchant-default levels, or None. `source` is the contract
    enum: `<source>_<match_type>` for a rule, else `recent_memory` /
    `merchant_default` / `none`.
    """
    candidates = [r for r in rules if _rule_matches(r, normalized_name)]
    if candidates:
        candidates.sort(
            key=lambda r: (
                0 if r["source"] == "user_correction" else 1,    # user before system
                0 if r["match_type"] == "merchant_exact" else 1,  # exact before contains
                -r["updated_at"].timestamp(),                     # newest correction first
            )
        )
        top = candidates[0]
        return top["category_id"], top["category_key"], f"{top['source']}_{top['match_type']}"
    if memory is not None:
        return memory[0], memory[1], "recent_memory"
    if default is not None:
        return default[0], default[1], "merchant_default"
    return None, None, "none"


if __name__ == "__main__":
    from datetime import datetime, timezone

    def _r(mt, mv, src, cat, key, day):
        return {"match_type": mt, "match_value": mv, "source": src,
                "category_id": cat, "category_key": key,
                "updated_at": datetime(2026, 6, day, tzinfo=timezone.utc)}

    exact = _r("merchant_exact", "wolt", "user_correction", "c1", "eating_out", 14)
    contains = _r("merchant_contains", "wol", "user_correction", "c2", "shopping", 15)
    assert resolve_suggestion([exact, contains], "wolt")[2] == "user_correction_merchant_exact"
    assert resolve_suggestion([exact, contains], "wolt tel aviv")[2] == "user_correction_merchant_contains"
    assert resolve_suggestion([], "golda") == (None, None, "none")
    # recent-memory sits below rules, above merchant default
    assert resolve_suggestion([], "golda", memory=("cm", "groceries")) == ("cm", "groceries", "recent_memory")
    assert resolve_suggestion([], "golda", default=("c9", "transport")) == ("c9", "transport", "merchant_default")
    assert resolve_suggestion([], "golda", memory=("cm", "k"), default=("c9", "t"))[2] == "recent_memory"
    assert resolve_suggestion([exact], "wolt", memory=("cm", "k"))[2] == "user_correction_merchant_exact"
    # newest correction wins on a tie (two exacts, same key, different days)
    older = _r("merchant_exact", "aroma", "user_correction", "cOLD", "k", 10)
    newer = _r("merchant_exact", "aroma", "user_correction", "cNEW", "k", 20)
    assert resolve_suggestion([older, newer], "aroma")[0] == "cNEW"
    print("ok")

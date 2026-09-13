"""Optional post-save rule offers (API §8; merchant normalization §10/§12)."""
from sqlalchemy import text

from app.db import get_sessionmaker

# Whole normalized names only: "Cafe Greg" remains a specific merchant.
_GENERIC_PAYEES = {
    "market", "cafe", "kiosk", "makolet", "paybox", "bit", "transfer", "atm",
    "other", "misc", "shop", "store", "isracard", "max", "cal",
    "מכולת", "קיוסק", "קפה", "חנות", "ביט", "פייבוקס", "כספומט", "העברה",
    "העברה יוצאת", "העברה נכנסת", "חיוב כרטיס אשראי", "עמלה", "ריבית",
    "ישראכרט", "מקס", "כאל",
}


async def quick_add_rule_prompt(transaction, user_id: str, normalized_name: str | None) -> dict:
    if (not transaction.merchant_id or not transaction.category_id
            or not normalized_name or normalized_name in _GENERIC_PAYEES):
        return {"offer": False}

    async with get_sessionmaker()() as session:
        eligibility = (await session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM category_rules r
                WHERE r.user_id = :user_id AND r.is_active = true
                  AND r.match_type = 'merchant_exact' AND r.match_value = :name
            ) AS has_exact_rule,
            (SELECT count(*) FROM (
                SELECT 1 FROM transactions t
                WHERE t.user_id = :user_id AND t.merchant_id = CAST(:merchant AS uuid)
                  AND t.category_id = CAST(:category AS uuid)
                  AND t.source = 'manual' AND t.is_card_settlement = false
                LIMIT 2
            ) repeated) AS category_uses
        """), {
            "user_id": user_id, "name": normalized_name,
            "merchant": transaction.merchant_id, "category": transaction.category_id,
        })).mappings().one()
    if eligibility["has_exact_rule"]:
        return {"offer": False}
    if transaction.category_key == "other_spending" and eligibility["category_uses"] < 2:
        return {"offer": False}
    return {
        "offer": True, "merchant_id": transaction.merchant_id,
        "suggested_category_id": transaction.category_id,
        "suggested_category_key": transaction.category_key,
    }

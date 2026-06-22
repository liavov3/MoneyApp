"""Canonical seed data — the 22 system categories (CATEGORY_TAXONOMY §10).

Single source of truth shared by the Alembic data migration and the tests.
14 consumer_spending + 8 bank_movement. Canonical keys include
`interest_bank_fee` and `cash_deposit_withdrawal` (NOT the prose aliases
`bank_fee_interest` / `cash_movement`). Every row:
  is_system = true, user_id = NULL, parent_id = NULL,
  included_in_committed_projection = false.
"""

from __future__ import annotations

from typing import NamedTuple


class SeedCategory(NamedTuple):
    key: str
    label_en: str
    label_he: str
    layer: str
    included_in_actual_spending: bool
    included_in_cash_flow: bool


# 14 consumer_spending: in_actual_spending=true, in_cash_flow=false.
_CONSUMER = [
    ("groceries", "Groceries", "קניות מזון / סופר"),
    ("eating_out", "Eating out", "אוכל בחוץ"),
    ("transport", "Transport", "תחבורה"),
    ("car_fuel", "Car / fuel", "רכב / דלק"),
    ("shopping", "Shopping", "קניות"),
    ("entertainment", "Entertainment", "בידור ופנאי"),
    ("subscriptions", "Subscriptions", "מנויים"),
    ("health", "Health", "בריאות"),
    ("education", "Education", "לימודים"),
    ("home", "Home", "בית"),
    ("gifts", "Gifts", "מתנות"),
    ("travel", "Travel", "נסיעות / חופשות"),
    ("personal_care", "Personal care", "טיפוח אישי"),
    ("other_spending", "Other spending", "הוצאות אחרות"),
]

# 8 bank_movement: in_actual_spending=false, in_cash_flow=true.
_BANK = [
    ("income", "Income", "הכנסה"),
    ("incoming_transfer", "Incoming transfer", "העברה נכנסת"),
    ("outgoing_transfer", "Outgoing transfer", "העברה יוצאת"),
    ("credit_card_settlement", "Credit card payment / settlement", "חיוב כרטיס אשראי"),
    ("loan_payment", "Loan payment", "תשלום הלוואה"),
    ("interest_bank_fee", "Interest / bank fee", "ריבית / עמלה"),
    ("cash_deposit_withdrawal", "Cash deposit / withdrawal", "הפקדה / משיכת מזומן"),
    ("other_bank_movement", "Other bank movement", "תנועה בנקאית אחרת"),
]


SEED_CATEGORIES: list[SeedCategory] = [
    SeedCategory(k, en, he, "consumer_spending", True, False) for (k, en, he) in _CONSUMER
] + [
    SeedCategory(k, en, he, "bank_movement", False, True) for (k, en, he) in _BANK
]


assert len(SEED_CATEGORIES) == 22, "Expected exactly 22 seed categories"
assert len({c.key for c in SEED_CATEGORIES}) == 22, "Seed keys must be unique"

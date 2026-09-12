---
name: moneyapp-money-correctness
description: Protect MoneyApp financial semantics for expenses, income, refunds, savings, goals, monthly totals, recurring commitments, and projections. Use for any financial calculation, aggregation, sign, amount conversion, or month-boundary change.
---

# MoneyApp Money Correctness

Treat financial calculations as correctness-critical.

## Required invariants

- Store and calculate authoritative money as integer agorot. Accept user-facing decimals as strings or exact decimal values and reject excess precision; never round silently or use binary-float arithmetic for money.
- Preserve the current transaction sign contract. Expenses are negative. Do not classify refunds as income, or change income/refund/adjustment behavior, without an explicit contract decision and regression tests.
- Goals and displayed caps are positive magnitudes and are not transaction rows.
- Use explicit date-only month boundaries: `occurred_on >= month_start AND occurred_on < next_month_start`. Test December/January and leap-year boundaries when relevant.
- Calculate authoritative totals in the backend from the complete scoped dataset. A paginated response, UI list, page limit, or first-N collection is never a valid aggregate source.
- Keep actual spending, cash flow, and recurring projections distinct. Never double count a template and a real transaction or expose an ambiguous blended total.
- Preserve server-resolved ownership and category inclusion rules in every aggregate.

## Review questions

- Which transaction types contribute to this value, and with what sign?
- Are uncategorized rows, refunds, income, adjustments, settlements, imports, and inactive templates handled intentionally?
- Does the selected month affect every displayed value consistently?
- Can the result change incorrectly after the collection exceeds one page?

## Regression coverage

Add focused exact-value tests for the behavior touched. Include relevant cases for agorot precision, zero/negative input, sign transitions, refunds, month boundaries, more than one page of transactions, inactive/out-of-month recurring templates, and actual-versus-projected separation.

Report expected equations and exact integer results; "looks right" is not sufficient evidence.

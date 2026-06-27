---
name: moneyapp-contract-guard
description: MoneyApp backend invariants checklist. Invoke BEFORE starting or claiming done any backend slice that touches transactions, money, categories, merchants, recurring templates, Home, auth, logging, or the API contract. Reminds Claude of the frozen money/ownership/privacy/contract rules so a slice does not drift. Use when the user says "contract guard", "moneyapp invariants", or starts a backend endpoint slice.
---

# MoneyApp Contract Guard

Run this checklist before writing a backend slice and again before claiming it
complete. The specs in `docs/` are FROZEN — match them field-for-field; if the
code conflicts with a frozen doc, STOP and report the exact sections.

## Auth & ownership
- `user_id` is **server-resolved only** (`require_principal`); never read or
  trusted from the client body or query. A forged `user_id` is ignored.
- Ownership mismatch → **404 `not_found`, never 403**. Missing row and
  malformed UUID also → 404. Responses stay generic; existence never leaks.

## Money (API_CONTRACT §14, app/money.py)
- Stored as **signed integer agorot** in `amount_minor` (bigint).
- Parse with `parse_amount_to_minor` — **Decimal/string only, never float**.
- `>2` decimals → `too_many_decimals` (422), **never silently round**.
- `0` → `zero_amount`; negative input → `negative_amount` (422).
- `expense` → negative; `income`/`refund`/`adjustment` → positive.
- `amount_minor <> 0` (DB check). A rejected amount mutates nothing.

## Errors & privacy
- Error envelope `{ error: { code, message, request_id, field_errors? } }`,
  generic content-free messages.
- Logs via `log_event` with allow-listed keys only. NEVER log amount, note,
  raw input, merchant text, correction content, email, or tokens — including on
  the `except` path.
- Never print the Neon URL/password or `DEV_BEARER_TOKEN`. `backend/.env` stays
  untracked.

## Domain rules (when the slice reaches them)
- Recurring templates create **zero** real transactions (projection only).
- Home never blends **actual spending** with **projected commitments**.
- Merchant fuzzy / cross-script matches never silently merge.
- Category rules **update-not-stack** (`UNIQUE(user_id, match_type, match_value)`).

## Done means
- `cd backend && python -m alembic upgrade head` clean, and
  `python -m pytest` green (0 unexpected skips) BEFORE claiming a slice done.
- Slice stayed small — only the requested endpoint, no out-of-scope features.

# Money App — API Contract (v0.0.1, manual-first)

Status: API specification only. No code, no endpoint implementations, no migrations. This document defines the REST/JSON contract that v0.0.1 freezes for the manual-first build. It is written against the FROZEN data model in docs/DATABASE_SCHEMA_V0_0_1.md and must match it exactly.
Owner: backend-api-engineer (lead), synthesizing product-architect, database-engineer, mobile-ux-designer, security-privacy-engineer, and qa-tester perspectives.
Governing decision: docs/MANUAL_FIRST_MVP_REVISION.md (2026-06-14) — v0.0.1 is manual-first; fast Quick Add is the primary loop. This supersedes the import-first v0.0.1 scope in docs/MVP_EXECUTION_ALIGNMENT.md.
Inputs (all read): docs/PRD_V0_1.md, docs/MANUAL_FIRST_MVP_REVISION.md, docs/CATEGORY_TAXONOMY.md, docs/MERCHANT_NORMALIZATION_SPEC.md, docs/QUICK_ADD_UX_SPEC.md, docs/DATABASE_SCHEMA_V0_0_1.md (FROZEN entities), docs/IMPORT_PIPELINE_SPEC.md (for deferred-endpoint awareness).
Firm invariants carried forward unchanged: REST/JSON; small API surface; manual-first; Quick Add fast; amount-only save works; merchant/category optional; save-first then enrich-after (prompts never block save); recurring = projection only (creates NO transactions); Home separates actual vs projected (never one blended total without labels); money is signed integer minor units (agorot) internally with ILS default; the API accepts decimal user input but normalizes to agorot; `user_id` is server-resolved and never client-supplied; raw merchant text / amount / note / raw input / correction content are NEVER logged; all user content is sensitive; NO AI/RAG endpoints; NO bank-import endpoints except clearly marked deferred; NO public SaaS / multi-user.
Anything labelled "assumption" is an implementation judgement by the author, not an established upstream fact.
Date: 2026-06-14

---

## 1. Purpose

This contract is the HTTP boundary for manual-first v0.0.1. It serves exactly two clients-of-record — the Quick Add capture flow and the Home dashboard — plus the supporting enrichment flows (merchant autocomplete, category suggestion, the "Always categorize…?" rule promotion, the cross-script "Same as Golda?" alias confirmation, transaction editing, and recurring-template management). It is written against the seven active tables frozen in DATABASE_SCHEMA_V0_0_1.md: `users`, `transactions`, `merchants`, `merchant_aliases`, `categories`, `category_rules`, `recurring_expense_templates`.

What this API SUPPORTS in v0.0.1:
- Listing the 22 seeded categories (14 consumer + 8 bank-movement) with their flags so the client can filter Quick Add to the 14 consumer categories.
- Merchant autocomplete / suggestion / resolution through the confidence ladder (exact > alias_exact > normalized_exact > recent_suggestion > contains > fuzzy_possible > none), with confirmation-required signalling and NO fuzzy auto-merge.
- Quick Add transaction creation: amount-only, amount+merchant, amount+merchant+category, default-today date, optional note, `source=manual`, `transaction_type=expense` by default, with a non-blocking duplicate-looking soft warning and a non-blocking large-amount confirmation.
- Transaction list / detail / edit / delete.
- Category correction and rule promotion (upsert, update-not-stack, user_correction authoritative), with explicit optional bulk apply.
- Merchant alias confirmation (user_confirmed, cross-script, no silent merge).
- Recurring expense template CRUD (projection-only; creates NO transactions).
- The Home dashboard rollups with actuals and projection ALWAYS returned as separate, labelled fields.

What this API INTENTIONALLY DEFERS (section 16): AI coach, RAG, bank-import preview/commit, itemized card import, insights, monthly summaries, open banking, push notifications, public auth/billing. None of the deferred tables (`accounts`, `import_batches`, `monthly_summaries`, `embeddings`, etc.) appears in the active contract. The deferred bank-import endpoints are listed only as clearly-marked future shapes so the v0.0.2 author has a target, never as live routes.

The discipline: a small surface that serves the five-second Quick Add and the five-second Home without workarounds, matches the frozen schema field-for-field, and never logs sensitive content.

---

## 2. API principles

1. Manual-first. Every active endpoint exists to serve manual capture or its reflection on Home. There is no import, AI, or insight route in v0.0.1.
2. Quick Add is fast. `POST /transactions/quick-add` is the hottest path. It requires only an amount. Merchant and category are optional. The server never gates the save on enrichment, lookups, or prompts.
3. Amount-only save is supported and first-class. A request with just `amount` (and a server-defaulted today's date) creates a valid transaction with `merchant_id=null` and `category_id=null` (uncategorized). This is not a degraded path.
4. Merchant and category are optional. Both are nullable on the transaction. Uncategorized (`category_id=null`) and merchant-less (`merchant_id=null`) are first-class, correctable states — never coerced into "Other".
5. Save-first, enrich-after. Prompts ("Always categorize…?", "Same as Golda?", duplicate-looking, large-amount) NEVER block the save. The save endpoint persists first and returns enrichment SUGGESTIONS in the response; the client surfaces them post-save; the user acts via separate, explicit follow-up endpoints (`POST /transactions/{id}/categorize`, `POST /merchants/{id}/aliases`).
6. Recurring = projected commitments, not actual transactions. Recurring template endpoints create/read/update/deactivate `recurring_expense_templates` rows ONLY. No template endpoint ever creates a `transactions` row. This is the single most important double-counting guard.
7. Home separates actual vs projected. `GET /home` returns `spent_so_far` (actual, Layer A) and `committed_amount` / `upcoming_commitments` (projected, Layer B) as DISTINCT fields inside a clearly-labelled `known_this_month` object. There is NEVER a single blended total.
8. Privacy-first logging. No request or response is ever logged with raw merchant text, note, amount, or correction content. Safe logs carry only: request id, endpoint name, status code, duration bucket, validation error code, confidence-level enum, and row counts (section 15).
9. REST/JSON, small surface. Resource-oriented routes, standard HTTP verbs and status codes, one stable error envelope, JSON in and out, snake_case keys, UTC timestamps, date-only financial dates, signed integer minor units in agorot on output.
10. Server-side authorization on every user-owned resource. `user_id` is resolved server-side from the authenticated principal (section 3); the client never supplies it. Every read and write filters by the resolved `user_id`. A resource owned by another principal is reported as 404, not 403 (section 5).

---

## 3. Auth and user model for v0.0.1

Simplest acceptable assumption: single-user, local/dev mode. v0.0.1 is a personal tool for exactly one user (PRD §3; MANUAL_FIRST_MVP_REVISION §1). There is no public sign-up, no multi-user, no billing.

Firm rules:
- The client NEVER supplies `user_id`. The server resolves the current user server-side and scopes every query to that `user_id`. There is no endpoint, body field, or query parameter through which a client can name a different user. `user_id` does not appear in any request body in this contract.
- Current-user resolution (recommended): a server-resolved "current user" via a single local dev principal. Recommended mechanism: a static, server-side dev bearer token presented as `Authorization: Bearer <dev_token>` that maps to the single seeded `users` row. The token is held in server config / a secrets manager, NEVER in the repo and NEVER in the mobile bundle (PRD §15). In a pure-local single-process build the principal may instead be resolved from a server-side "current local user" record; either way the resolution is server-side and opaque to the client.
- Every user-owned resource is authorized server-side. Before any read/write of a `transactions`, `merchants`, `merchant_aliases`, `category_rules`, or `recurring_expense_templates` row, the server confirms the row's `user_id` equals the resolved principal. System `categories` rows (`user_id IS NULL`) are readable by any principal (shared, read-only seed).
- Future auth is additive without changing core resource contracts. When real auth lands (PRD Phase 1 / later multi-user), only the principal-resolution layer changes (a real token/session replaces the dev token). The resource routes, request bodies, and response shapes in this document do not change, because none of them mentions `user_id`. This is the whole reason `user_id` is server-resolved and absent from every payload.
- Missing/invalid principal → `401 unauthorized` with the standard error envelope (section 5). No resource is ever returned without a resolved principal.

Out of scope for v0.0.1 auth: registration, password reset, OAuth, sessions UI, device-unlock flows (that is a client concern), multi-user tenancy, and any billing/subscription. These are deferred (section 16).

---

## 4. Shared API conventions

- Base URL: `/api/v1`. All paths below are relative to this prefix (e.g. `POST /api/v1/transactions/quick-add`). Versioning the URL keeps v0.0.2 additive.
- Content type: `application/json; charset=utf-8` for all request and response bodies. UTF-8 is mandatory (Hebrew merchant text).
- IDs: `uuid` strings (e.g. `"b3f1c2a4-5e6d-4f7a-8b9c-0d1e2f3a4b5c"`), matching the schema's `uuid` primary keys. IDs are opaque; clients must not parse them.
- Date format (financial dates): `occurred_on` and `next_expected_date` are date-only strings `YYYY-MM-DD` (e.g. `"2026-06-14"`). No time component — financial dates are date-only by firm invariant.
- Timestamp format (metadata): `created_at` / `updated_at` / `last_seen_at` are RFC 3339 UTC strings with a `Z` suffix (e.g. `"2026-06-14T08:31:05Z"`), matching the schema's `timestamptz` UTC columns.
- Currency: ISO-4217 three-letter code, `"ILS"` default. Returned on money-bearing objects as `currency`.
- Amount INPUT format (request → server): the client MAY send money as either a JSON number or a decimal string in MAJOR units (shekels), e.g. `33`, `33.5`, or `"33.50"`. The server normalizes to signed integer agorot (section 14). A decimal string is accepted to avoid binary float rounding on the wire; a JSON number is also accepted for client convenience. Input is always non-negative major units for an `expense`; the sign is applied server-side from `transaction_type` (section 14). The request never carries `amount_minor`.
- Amount OUTPUT format (server → client): money is always returned as `amount_minor` (signed integer agorot) plus `currency`. The server does NOT return a pre-formatted major-unit string; the client formats `amount_minor / 100` for display. This keeps the wire representation exact and integer. Example: a ₪33.50 expense is returned as `{ "amount_minor": -3350, "currency": "ILS" }`. (Sign convention per schema §5: an `expense` is stored negative; `income`/`refund` positive. Home sums use magnitude — section 13.)
- Enums: lowercase snake_case strings, matching the schema CHECK constraints exactly: `transaction_type` ∈ {`expense`,`income`,`refund`,`adjustment`}; `source` ∈ {`manual`,`bank_import`,`card_import`} (only `manual` is produced in v0.0.1); `merchant_aliases.source` ∈ {`user_confirmed`,`import_parsed`,`system_suggested`}; `category_rules.match_type` ∈ {`merchant_exact`,`merchant_contains`}; `category_rules.source` ∈ {`system`,`user_correction`}; `cadence` ∈ {`weekly`,`monthly`,`yearly`}; `categories.layer` ∈ {`consumer_spending`,`bank_movement`}; merchant `confidence` ∈ {`exact`,`alias_exact`,`normalized_exact`,`recent_suggestion`,`contains`,`fuzzy_possible`,`none`}.
- Pagination convention: cursor-based (opaque cursor), chosen over offset/limit. Justification: transaction lists grow over time and are ordered by `occurred_on DESC, created_at DESC` (schema §10); offset pagination drifts and re-scans as new rows are inserted at the top during active logging, whereas an opaque cursor is stable under concurrent inserts and cheap on the `(user_id, occurred_on)` index. Requests take `?limit=` (default 50, max 100) and `?cursor=`; responses return `{ "items": [...], "next_cursor": "<opaque|null>" }`. `next_cursor` is `null` when there are no more rows. The cursor encodes `(occurred_on, created_at, id)` server-side and is opaque to the client.
- Validation philosophy: validate every input; reject with `422 validation_error` and a field-level error list (section 5). Never trust client-supplied sign, `user_id`, `amount_minor`, `source` other than manual, or system-category mutation.
- Privacy-safe logging convention: every endpoint logs only `{ request_id, endpoint, status, duration_bucket, validation_error_code?, confidence_level?, row_count? }`. No body field that contains merchant text, note, amount, or correction content is ever logged (section 15).

---

## 5. Error response model

Standard error envelope (every non-2xx response):

```json
{
  "error": {
    "code": "validation_error",
    "message": "One or more fields are invalid.",
    "request_id": "req_7f3a9c20",
    "field_errors": [
      { "field": "amount", "code": "zero_amount", "message": "Enter an amount above 0." }
    ]
  }
}
```

- `code` — a stable machine-readable enum (snake_case). Clients branch on this, never on `message`.
- `message` — a short, safe, human-readable summary. It NEVER contains merchant text, note content, amounts tied to identity, or any correction content. Generic by design.
- `request_id` — the same id used in safe logs, so a user-reported issue can be traced without logging content.
- `field_errors` — optional array, present for `validation_error`. Each carries `{ field, code, message }`; `code` is an enum (e.g. `empty_amount`, `zero_amount`, `negative_amount`, `too_many_decimals`, `invalid_currency`, `invalid_date`, `invalid_enum`, `unknown_category`, `not_consumer_category`, `unknown_merchant`).

Standard `code` values and the HTTP status they pair with:

| code | HTTP | When |
|---|---|---|
| `validation_error` | 422 | A field failed validation. `field_errors` present. Example: empty/zero/negative amount, >2 decimal places, unknown enum, Quick Add category not in the consumer layer. Message stays generic: "One or more fields are invalid." |
| `not_found` | 404 | The resource does not exist OR is not owned by the resolved principal. Ownership mismatch is reported as 404, not 403 (see below). Message: "Resource not found." Never echoes an id-derived detail. |
| `conflict` | 409 | A write violates a uniqueness/state invariant in a way the client should resolve — e.g. attempting to create a second merchant for a `normalized_merchant_name` that already exists, or a rule upsert race. (Note: the normal rule-correction path UPDATES rather than conflicts; 409 is for genuine concurrent-create collisions.) Message: "This conflicts with existing data." |
| `unauthorized` | 401 | No resolved principal / invalid dev token (section 3). Message: "Authentication required." |
| `unsupported_operation` | 403 | A deliberately-blocked operation, e.g. mutating a system category, or calling a deferred endpoint stub. Message: "This operation is not supported." (Distinct from ownership, which is 404.) |
| `backend_unavailable` | 503 | A dependency (database) is unreachable. Message: "Service temporarily unavailable — your entry was not saved. Try again." The client preserves typed input and offers retry (QUICK_ADD_UX_SPEC §11). |
| `internal_error` | 500 | Unexpected server error. Message: "Something went wrong. Try again." No stack, no content, ever. |

Ownership mismatch → 404, not 403 (recommended, firm): when a principal requests a `transactions`/`merchants`/`category_rules`/`recurring_expense_templates`/`merchant_aliases` row owned by a different `user_id`, the server returns `404 not_found`, identical to a truly missing row. Returning 403 would confirm the resource EXISTS, leaking the existence of another user's data. 404-for-both reveals nothing. (In single-user v0.0.1 this is rarely exercised, but it is built now so multi-user later is safe by construction, consistent with the schema's user_id-everywhere discipline.)

Duplicate-looking transaction is NOT an error (firm): a near-identical recent entry (same amount + merchant + `occurred_on`) does NOT produce a 4xx. The save SUCCEEDS (201) and the response carries a non-blocking soft `warnings` array (section 8). Two coffees happen; the API never blocks a legitimate repeat. This is the save-first principle made concrete: a warning is data on a 201, never an error.

No message ever leaks sensitive content: error messages are generic and content-free. A validation message says "Enter an amount above 0", never the amount; a not_found says "Resource not found", never which merchant/note was involved. This is enforced as a review rule on every message string.

---

## 6. Category endpoints

### GET /categories

Returns all 22 seeded system categories with their flags. Read-only in v0.0.1 (no create/update/delete of categories; system rows are immutable — `unsupported_operation` if mutation is attempted).

- Method/path: `GET /api/v1/categories`
- Auth: required (resolved principal). System categories are shared; the response is identical for any principal in v0.0.1.
- Request: none. (Optional future filter `?layer=consumer_spending` is NOT required; the client filters locally — the set is tiny and static.)
- Response 200:

```json
{
  "items": [
    {
      "id": "c1000000-0000-0000-0000-000000000001",
      "key": "groceries",
      "label_en": "Groceries",
      "label_he": "קניות מזון / סופר",
      "layer": "consumer_spending",
      "included_in_actual_spending": true,
      "included_in_cash_flow": false,
      "is_system": true
    },
    {
      "id": "c1000000-0000-0000-0000-000000000015",
      "key": "income",
      "label_en": "Income",
      "label_he": "הכנסה",
      "layer": "bank_movement",
      "included_in_actual_spending": false,
      "included_in_cash_flow": true,
      "is_system": true
    }
  ]
}
```

- Returned fields per category: `id`, `key`, `label_en`, `label_he`, `layer`, `included_in_actual_spending`, `included_in_cash_flow`, `is_system`. (`included_in_committed_projection` is omitted: it is `false` for every category row by schema invariant — projection is a template property, not a category flag — so returning it would only invite misuse. If a future client needs it, it is always `false`.)
- Count: exactly 22 — 14 `consumer_spending` (with `included_in_actual_spending=true`) and 8 `bank_movement` (with `included_in_cash_flow=true`). Keys match the schema seed exactly, including canonical `interest_bank_fee` and `cash_deposit_withdrawal`.
- Client filtering for Quick Add: the Quick Add picker shows ONLY `layer == "consumer_spending"` categories (the 14). The 8 `bank_movement` (Layer C) categories are NEVER offered in manual entry (QUICK_ADD_UX_SPEC §7; CATEGORY_TAXONOMY §11). The client filters locally on `layer`; the server enforces the same rule on write (a Quick Add or categorize request with a non-consumer category is rejected `422 not_consumer_category` — sections 8, 10, 14).
- Errors: `401 unauthorized`, `503 backend_unavailable`, `500 internal_error`.
- Caching: the set is static; the client may cache it for the session. (Assumption: a long client-side cache is safe because keys/flags are frozen.)
- Tests: returns exactly 22 rows; all 14 consumer rows have `included_in_actual_spending=true` and `included_in_cash_flow=false`; all 8 bank rows have the inverse; canonical keys present; no category is mutable.

---

## 7. Merchant suggestion endpoints

These serve Quick Add autocomplete and resolution. They are READ/SUGGEST only — they never create a merchant or an alias and never auto-merge. Creation happens implicitly on save (section 8) or explicitly on alias confirmation (section 11). Every response carries the `confidence` level and `requires_confirmation`, NOT an auto-merge.

### GET /merchants/suggestions?query=

Autocomplete + resolution as the user types a merchant.

- Method/path: `GET /api/v1/merchants/suggestions?query=<text>&limit=<n>`
- Auth: required. Scoped to the principal's merchants only.
- Request query params: `query` (the typed merchant text, required, may be Hebrew/English/mixed); `limit` (optional, default 8, max 20).
- Behaviour: the server normalizes `query` per MERCHANT_NORMALIZATION_SPEC §4 (deterministic; whitespace/invisible-char strip, NFC, English case-fold, Hebrew preserved) and resolves against the principal's `merchants` and `merchant_aliases` via the confidence ladder (§7 of the merchant spec). It returns ranked candidates, each with its confidence and whether confirmation is required. It NEVER auto-merges; cross-script and `contains` candidates are surfaced as `requires_confirmation: true`.
- Response 200:

```json
{
  "query_confidence": "recent_suggestion",
  "auto_select_merchant_id": null,
  "items": [
    {
      "merchant_id": "m1000000-0000-0000-0000-0000000000aa",
      "display_name": "Golda",
      "confidence": "recent_suggestion",
      "requires_confirmation": false,
      "matched_via": "merchant",
      "suggested_category_id": "c1000000-0000-0000-0000-000000000002",
      "suggested_category_key": "eating_out",
      "suggested_category_source": "recent_memory"
    },
    {
      "merchant_id": "m1000000-0000-0000-0000-0000000000bb",
      "display_name": "Golda Givatayim",
      "confidence": "contains",
      "requires_confirmation": true,
      "matched_via": "merchant",
      "suggested_category_id": null,
      "suggested_category_key": null,
      "suggested_category_source": "none"
    }
  ]
}
```

- `query_confidence` — the single strongest confidence level the query reached overall (the enum). `auto_select_merchant_id` — non-null ONLY when the query resolved at `exact`, `alias_exact`, or `normalized_exact` (same-script, deterministic), telling the client it may auto-select silently. For `recent_suggestion`/`contains`/`none` it is `null` (the user must tap).
- Per-item fields: `merchant_id`, `display_name`, `confidence`, `requires_confirmation` (true for `contains` and cross-script candidates — never auto-merge), `matched_via` (`merchant` | `alias`), and the pre-resolved category suggestion (`suggested_category_id`, `suggested_category_key`, `suggested_category_source` ∈ {`user_correction_merchant_exact`,`user_correction_merchant_contains`,`system_merchant_exact`,`system_merchant_contains`,`recent_memory`,`merchant_default`,`none`} — the precedence ladder level that resolved, section 10/§9).
- Confidence governs action, never auto-merge: `exact`/`alias_exact`/`normalized_exact` → client MAY auto-select (`auto_select_merchant_id` set). `recent_suggestion`/`contains` → suggestions requiring a tap. Cross-script (e.g. typed `גולדה` while `Golda` exists) is surfaced as a candidate with `requires_confirmation: true` and `confidence: contains` or `none`; linking happens only via `POST /merchants/{id}/aliases` (section 11). `fuzzy_possible` behaves as `none` in v0.0.1 (no fuzzy auto-merge).
- Request/response example (cross-script):

```
GET /api/v1/merchants/suggestions?query=%D7%92%D7%95%D7%9C%D7%93%D7%94   (query = "גולדה")
```

```json
{
  "query_confidence": "none",
  "auto_select_merchant_id": null,
  "items": [
    {
      "merchant_id": "m1000000-0000-0000-0000-0000000000aa",
      "display_name": "Golda",
      "confidence": "none",
      "requires_confirmation": true,
      "matched_via": "merchant",
      "cross_script_candidate": true,
      "suggested_category_id": null,
      "suggested_category_key": null,
      "suggested_category_source": "none"
    }
  ]
}
```

- Privacy: the request `query` and every returned `display_name` are sensitive and NEVER logged. Logs carry only `query_confidence` enum and item count (section 15).
- Errors: `401`, `422 validation_error` (empty query), `503`, `500`.
- Tests: exact existing merchant → `auto_select_merchant_id` set, `confidence=exact`; cross-script → candidate with `requires_confirmation=true`, no auto-select; `contains` branch → suggestion, never auto-merge; typo "Goldaa" → behaves as `none` (no fuzzy merge); raw query never appears in logs.

### GET /merchants/recent

The recent/frequent merchant chips shown under the merchant field before/while typing.

- Method/path: `GET /api/v1/merchants/recent?limit=<n>`
- Auth: required. Principal-scoped.
- Request: `limit` (optional, default 8, max 20).
- Response 200:

```json
{
  "items": [
    {
      "merchant_id": "m1000000-0000-0000-0000-0000000000aa",
      "display_name": "Golda",
      "suggested_category_id": "c1000000-0000-0000-0000-000000000002",
      "suggested_category_key": "eating_out",
      "suggested_category_source": "recent_memory",
      "last_used_at": "2026-06-13T19:02:00Z"
    }
  ]
}
```

- Ordering: by recency then frequency, using `merchants.updated_at DESC` / alias `last_seen_at` (schema §12 indexes `(user_id, updated_at DESC)`). Each chip carries the pre-resolved category suggestion so a one-tap selection auto-fills the category.
- Empty state: `{ "items": [] }` when no history exists; the client shows no chip row (QUICK_ADD_UX_SPEC §6).
- Privacy: `display_name` never logged.
- Tests: returns most-recent-first; includes per-merchant suggested category; empty array before any history.

---

## 8. Quick Add transaction endpoint

### POST /transactions/quick-add

The primary v0.0.1 endpoint. Creates one manual transaction. Amount is the only required field. Merchant and category are optional. Save is never blocked by enrichment, duplicates, or large amounts — those return as non-blocking response data.

- Method/path: `POST /api/v1/transactions/quick-add`
- Auth: required. `user_id` resolved server-side, never in the body.
- Request schema:

```json
{
  "amount": "33.50",
  "transaction_type": "expense",
  "merchant_input": "Golda",
  "merchant_id": null,
  "category_id": null,
  "occurred_on": null,
  "note": null,
  "confirm_large_amount": false,
  "currency": "ILS"
}
```

Field rules:
- `amount` (required) — JSON number or decimal string, MAJOR units, non-negative, ≤2 decimal places. Server normalizes to signed agorot (section 14).
- `transaction_type` (optional, default `expense`) — one of the four enum values. `income`/`refund` only when the client explicitly sets it (the "Mark as income/refund" toggle, QUICK_ADD_UX_SPEC §5). Default `expense`.
- `merchant_input` (optional) — the verbatim typed merchant text. If present and it does not resolve to an existing merchant via `exact`/`alias_exact`/`normalized_exact`, the server CREATES a new merchant from it (confidence `none` path) and stores the raw input as the merchant's first alias (schema §3.3/§6). Stored verbatim as `transactions.raw_merchant_input`. Sensitive; never logged.
- `merchant_id` (optional) — when the client already resolved/selected a merchant (e.g. tapped a recent chip or an `auto_select_merchant_id`), it sends the id directly. If both `merchant_id` and `merchant_input` are present, `merchant_id` wins and `merchant_input` is still stored as `raw_merchant_input`. The merchant must be owned by the principal (else `404`/`422 unknown_merchant`).
- `category_id` (optional) — a category to set explicitly. MUST be a `consumer_spending` (Layer A) category or omitted; a `bank_movement` category is rejected `422 not_consumer_category`. Omitted/null → uncategorized (first-class).
- `occurred_on` (optional) — `YYYY-MM-DD`; defaults to the server's current date (today) when null/omitted. Must not be absurdly future (assumption: reject dates more than ~1 day in the future as `422 invalid_date`, to catch typos, while allowing backdating freely).
- `note` (optional) — free text; stored; NEVER logged.
- `confirm_large_amount` (optional, default false) — see large-amount flow below.
- `currency` (optional, default the user's `base_currency`, i.e. `ILS`).

Server behaviour (save-first):
1. Validate `amount` and fields. On failure → `422 validation_error` (nothing persisted).
2. Resolve merchant (from `merchant_id`, else from `merchant_input` via the ladder; create-new on `none`). Never auto-merge cross-script; if `merchant_input` is a cross-script/`contains` candidate of an existing merchant, the server CREATES a new merchant (no silent merge) and returns an `alias_suggestion` in the response for the user to confirm later.
3. Resolve category: if `category_id` given, use it (validated consumer-layer); else if a merchant resolved, pre-fill via the precedence ladder (section 10/§9) ONLY as a returned suggestion — the saved `category_id` is set from a resolved rule/memory ONLY if the client did not explicitly clear it. (Assumption, matching QUICK_ADD_UX_SPEC §7: the client sends the suggested `category_id` it wants saved; the endpoint does not silently invent a category the client did not choose. If neither `category_id` nor a client-accepted suggestion is sent, the row is uncategorized.)
4. Normalize amount to signed agorot using `transaction_type` (section 14).
5. Persist a `transactions` row: `source='manual'`, `is_card_settlement=false`, `dedup_hash=null`, `occurred_on` defaulted, `merchant_id`/`category_id` as resolved (nullable).
6. Compute non-blocking response signals: `duplicate_warning` (if a near-identical recent row exists), `large_amount` confirmation need, `category_suggestion` metadata, `rule_prompt` (whether to offer "Always categorize…?"), and `alias_suggestion` (cross-script "Same as…?"). None of these blocks the save.

- Response 201:

```json
{
  "transaction": {
    "id": "t1000000-0000-0000-0000-0000000000f1",
    "amount_minor": -3350,
    "currency": "ILS",
    "transaction_type": "expense",
    "source": "manual",
    "merchant_id": "m1000000-0000-0000-0000-0000000000aa",
    "merchant_display_name": "Golda",
    "category_id": "c1000000-0000-0000-0000-000000000002",
    "category_key": "eating_out",
    "occurred_on": "2026-06-14",
    "note": null,
    "is_card_settlement": false,
    "created_at": "2026-06-14T08:31:05Z",
    "updated_at": "2026-06-14T08:31:05Z"
  },
  "warnings": [],
  "category_suggestion": {
    "category_id": "c1000000-0000-0000-0000-000000000002",
    "category_key": "eating_out",
    "source": "recent_memory"
  },
  "rule_prompt": {
    "offer": true,
    "merchant_id": "m1000000-0000-0000-0000-0000000000aa",
    "suggested_category_id": "c1000000-0000-0000-0000-000000000002",
    "suggested_category_key": "eating_out"
  },
  "alias_suggestion": null
}
```

- `transaction` — the persisted row. Money as `amount_minor` (signed agorot) + `currency`. `merchant_display_name` and `category_key` are convenience joins for immediate display.
- `warnings` — a possibly-empty array of non-blocking soft warnings (duplicate-looking, large-amount-confirmed-elsewhere). NEVER an error.
- `category_suggestion` — the resolved suggestion metadata (the precedence level via `source`), so the client can show what it filed it under. Null if uncategorized.
- `rule_prompt` — `{ offer: bool, ... }`. `offer:true` when the saved row has BOTH a merchant and a category AND no trusted `merchant_exact` rule exists yet, AND the merchant is not generic/transfer-like and not a one-off `other_spending` (MERCHANT_NORMALIZATION_SPEC §10). The client surfaces "Always categorize Golda as Eating out?" post-save; the user acts via `POST /transactions/{id}/categorize` (section 10). `offer:false` (or `null`) otherwise (e.g. amount-only).
- `alias_suggestion` — non-null when `merchant_input` was a cross-script/branch candidate of an existing merchant; `{ candidate_merchant_id, candidate_display_name, new_merchant_id }`. The client surfaces "Same as Golda?"; the user acts via `POST /merchants/{id}/aliases` (section 11). Never an auto-merge.

Duplicate-looking soft warning (recommended: save-then-warn). When a near-identical recent row exists (same `amount_minor`, same `merchant_id` (or both null), same `occurred_on`, within a short recency window — assumption: same day), the endpoint STILL returns `201` with the saved transaction AND a warning:

```json
"warnings": [
  { "code": "duplicate_looking", "message": "A similar entry was just added.",
    "similar_transaction_id": "t1000000-0000-0000-0000-0000000000e9" }
]
```

Justification for save-then-warn over a confirm-token handshake: the capture moment is sacred and a legitimate repeat (two coffees) is common (QUICK_ADD_UX_SPEC §11). Blocking the save behind a confirm token would add a round-trip and a decision exactly when we need zero friction, and risks losing the entry. Saving first guarantees the data is never at risk; the client shows "Looks like you just added ₪33 at Golda — keep it, or undo?" with an explicit `DELETE /transactions/{id}` (section 9) if the user decides it was a mistake. The warning is informational, not a gate.

Very-large-amount confirmation flow (non-blocking, two-call confirm). To catch fat-finger errors without judging spend (QUICK_ADD_UX_SPEC §11), an unusually large amount is confirmed by the client, never blocked by the server:
- First call with `confirm_large_amount:false` (default) and an amount at/above a threshold (assumption: ₪10,000, or well above the user's typical entry): the server STILL saves the transaction (save-first) and returns `201` with a warning `{ code: "large_amount", message: "That's a big one — confirm it's correct.", amount_minor: -1200000 }`. The transaction is persisted; the warning prompts the client to show "₪12,000 — save it?" with "Yes, keep" / "Edit".
- "Yes, keep" needs no further call (already saved). "Edit" uses `PATCH /transactions/{id}` to correct the amount, or `DELETE` to remove it. (Assumption: this keeps a single firm rule — the server never blocks a save — so the large-amount path is the same save-then-warn shape as duplicates. `confirm_large_amount:true` simply suppresses the warning when the client has already confirmed in a prior UI step, e.g. a re-submit after editing.)

Worked request/response examples:

(1) Amount-only (Mode A):

```
POST /api/v1/transactions/quick-add
{ "amount": 33 }
```
```json
{ "transaction": { "id": "...", "amount_minor": -3300, "currency": "ILS",
    "transaction_type": "expense", "source": "manual", "merchant_id": null,
    "merchant_display_name": null, "category_id": null, "category_key": null,
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T08:31:05Z", "updated_at": "2026-06-14T08:31:05Z" },
  "warnings": [], "category_suggestion": null,
  "rule_prompt": { "offer": false }, "alias_suggestion": null }
```

(2) Amount + merchant (Mode B):

```
POST /api/v1/transactions/quick-add
{ "amount": "33", "merchant_input": "Golda" }
```
```json
{ "transaction": { "id": "...", "amount_minor": -3300, "currency": "ILS",
    "transaction_type": "expense", "source": "manual",
    "merchant_id": "m...aa", "merchant_display_name": "Golda",
    "category_id": "c...02", "category_key": "eating_out",
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T08:31:05Z", "updated_at": "2026-06-14T08:31:05Z" },
  "warnings": [],
  "category_suggestion": { "category_id": "c...02", "category_key": "eating_out", "source": "recent_memory" },
  "rule_prompt": { "offer": true, "merchant_id": "m...aa",
    "suggested_category_id": "c...02", "suggested_category_key": "eating_out" },
  "alias_suggestion": null }
```

(3) Amount + merchant + category (Mode C):

```
POST /api/v1/transactions/quick-add
{ "amount": "33.50", "merchant_id": "m...aa", "category_id": "c...02" }
```
```json
{ "transaction": { "id": "...", "amount_minor": -3350, "currency": "ILS",
    "transaction_type": "expense", "source": "manual",
    "merchant_id": "m...aa", "merchant_display_name": "Golda",
    "category_id": "c...02", "category_key": "eating_out",
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T08:31:05Z", "updated_at": "2026-06-14T08:31:05Z" },
  "warnings": [],
  "category_suggestion": { "category_id": "c...02", "category_key": "eating_out", "source": "user_choice" },
  "rule_prompt": { "offer": true, "merchant_id": "m...aa",
    "suggested_category_id": "c...02", "suggested_category_key": "eating_out" },
  "alias_suggestion": null }
```

(4) Duplicate-looking warning:

```
POST /api/v1/transactions/quick-add
{ "amount": 33, "merchant_id": "m...aa" }   // a near-identical row exists today
```
```json
{ "transaction": { "id": "t...f2", "amount_minor": -3300, "currency": "ILS",
    "transaction_type": "expense", "source": "manual",
    "merchant_id": "m...aa", "merchant_display_name": "Golda",
    "category_id": "c...02", "category_key": "eating_out",
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T09:05:00Z", "updated_at": "2026-06-14T09:05:00Z" },
  "warnings": [ { "code": "duplicate_looking", "message": "A similar entry was just added.",
    "similar_transaction_id": "t...f1" } ],
  "category_suggestion": { "category_id": "c...02", "category_key": "eating_out", "source": "recent_memory" },
  "rule_prompt": { "offer": false }, "alias_suggestion": null }
```

(5) Very large amount confirmation flow:

```
POST /api/v1/transactions/quick-add
{ "amount": 12000, "merchant_input": "HomeCenter" }
```
```json
{ "transaction": { "id": "t...f3", "amount_minor": -1200000, "currency": "ILS",
    "transaction_type": "expense", "source": "manual",
    "merchant_id": "m...cc", "merchant_display_name": "HomeCenter",
    "category_id": null, "category_key": null,
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T09:10:00Z", "updated_at": "2026-06-14T09:10:00Z" },
  "warnings": [ { "code": "large_amount",
    "message": "That's a big one — confirm it's correct.", "amount_minor": -1200000 } ],
  "category_suggestion": null, "rule_prompt": { "offer": false }, "alias_suggestion": null }
```
The client shows "₪12,000 — save it?" with "Yes, keep" (already saved, no call) / "Edit" (`PATCH`) / "Undo" (`DELETE`).

- Errors: `401`; `422 validation_error` (empty/zero/negative amount, >2 decimals, non-consumer `category_id`, invalid enum, absurd-future date, unknown merchant); `503 backend_unavailable` (nothing saved, client preserves input and retries); `500 internal_error`.
- Rate limit: not required for single-user local v0.0.1; if added, a generous per-principal limit (assumption: not enforced now).
- Tests: amount-only persists uncategorized and counts as spend; merchant create-on-`none`; cross-script never auto-merges (returns `alias_suggestion`); non-consumer category rejected; duplicate returns 201+warning; large amount returns 201+warning; raw `merchant_input`/`note`/amount never logged.

---

## 9. Transactions endpoints

### GET /transactions

List the principal's transactions, filterable by month, category, or recency.

- Method/path: `GET /api/v1/transactions?month=YYYY-MM&category_id=<uuid>&uncategorized=<bool>&limit=<n>&cursor=<opaque>`
- Auth: required. Principal-scoped.
- Query params (all optional):
  - `month` — `YYYY-MM`; filters `occurred_on` within that calendar month. Omitted → recent across all months.
  - `category_id` — restrict to one category (the category-detail drill-down). `uncategorized=true` restricts to `category_id IS NULL` (the "needs a category" review); the two are mutually exclusive.
  - `limit` (default 50, max 100), `cursor` (opaque) — cursor pagination (section 4).
- Ordering: `occurred_on DESC, created_at DESC` (schema §10), on the `(user_id, occurred_on)` index.
- Response 200:

```json
{
  "items": [
    {
      "id": "t...f1",
      "amount_minor": -3300,
      "currency": "ILS",
      "transaction_type": "expense",
      "source": "manual",
      "merchant_id": "m...aa",
      "merchant_display_name": "Golda",
      "category_id": "c...02",
      "category_key": "eating_out",
      "occurred_on": "2026-06-14",
      "note": null,
      "is_card_settlement": false,
      "created_at": "2026-06-14T08:31:05Z",
      "updated_at": "2026-06-14T08:31:05Z"
    }
  ],
  "next_cursor": null
}
```

- Uncategorized rows are included and clearly identifiable by `category_id: null` / `category_key: null`.
- Errors: `401`, `422` (bad `month` format, both `category_id` and `uncategorized`), `503`, `500`.
- Tests: month filter buckets by `occurred_on`; category filter; uncategorized filter; cursor stable under concurrent inserts; amounts in agorot.

### GET /transactions/{id}

- Method/path: `GET /api/v1/transactions/{id}`
- Auth: required. Ownership enforced; another principal's row → `404` (section 5).
- Response 200: the single transaction object (same shape as the list item above, plus `raw_merchant_input` is NOT returned by default — it is sensitive and not needed for display; the client shows `merchant_display_name`).
- Errors: `401`, `404 not_found` (missing or not owned), `503`, `500`.

### PATCH /transactions/{id}

Edit merchant, category, note, amount, date, and/or `transaction_type`. Partial update — only provided fields change.

- Method/path: `PATCH /api/v1/transactions/{id}`
- Auth: required. Ownership enforced (→ 404 if not owned).
- Request schema (all fields optional; at least one required):

```json
{
  "amount": "30.00",
  "transaction_type": "expense",
  "merchant_id": "m...aa",
  "merchant_input": null,
  "category_id": "c...05",
  "occurred_on": "2026-06-13",
  "note": "split with Dana"
}
```
- `amount` re-normalized to agorot using the (possibly updated) `transaction_type`. Sign is recomputed server-side, never sent by the client.
- `category_id` must be a consumer-layer category or `null` (to clear to uncategorized); a `bank_movement` category → `422 not_consumer_category`.
- Setting `merchant_id: null` clears the merchant (→ merchant-less). `merchant_input` may set/create a merchant as in Quick Add.
- A category change here may make the success response offer a rule prompt (see below), but PATCH itself does NOT create a rule — rule promotion is the explicit `POST /transactions/{id}/categorize` (section 10). A silent PATCH changes only this transaction (CATEGORY_TAXONOMY §9). The PATCH response MAY include a `rule_prompt` object (same shape as Quick Add) when a category was changed for a merchant lacking a trusted rule.
- Response 200: the updated transaction object (plus optional `rule_prompt`).
- Transaction remains ACTUAL spending unless `transaction_type` is changed: editing amount/merchant/category/note/date keeps the row counting toward "Spent so far". Changing `transaction_type` to `income`/`refund`/`adjustment` changes how it nets (section 13). This is the only field that moves a row out of "expense" spend.
- Errors: `401`, `404`, `422 validation_error`, `409 conflict` (rare concurrent edit), `503`, `500`.
- Tests: amount edit re-normalizes sign; category cleared to null; non-consumer category rejected; `transaction_type` change moves it out of spend; PATCH alone creates no rule.

### DELETE /transactions/{id}

- Method/path: `DELETE /api/v1/transactions/{id}`
- Auth: required. Ownership enforced (→ 404 if not owned).
- Recommendation (firm): HARD delete for v0.0.1. Justification: this is a single-user personal tool; a mistaken or duplicate entry should simply disappear, and the schema's `ON DELETE` behavior plus user-scoped queries make a hard delete clean and safe (DATABASE_SCHEMA §13: deletion must be easy). There is no shared/audit requirement that a soft-delete tombstone would serve in v0.0.1, and a soft-delete flag would add `is_deleted` filtering to every Home/spend query (extra surface, more bug area) for no v0.0.1 benefit. The "undo" affordance for a just-saved duplicate is served by an immediate hard `DELETE` from the client's success state, not by a tombstone. (If future versions need recoverable deletion or audit, a soft-delete column is an additive change — but it is explicitly NOT in v0.0.1.)
- Response 204: no body.
- Errors: `401`, `404`, `503`, `500`.
- Tests: delete removes the row and it no longer counts toward spend; deleting another principal's row → 404; idempotent re-delete of an already-deleted id → 404.

---

## 10. Category correction and rule promotion

Two surfaces: a direct rule resource (`/category-rules`) and a transaction-centric helper (`/transactions/{id}/categorize`) that combines "set this transaction's category" with "optionally promote to a rule". Both honor: user confirmation required to create a rule; `source=user_correction`; `merchant_exact` + `merchant_contains`; update-not-stack via `UNIQUE(user_id, match_type, match_value)`; rules apply going forward; existing transactions are NOT auto bulk-updated (an explicit `apply_to_existing` flag, default false, offers it).

### POST /transactions/{id}/categorize

Categorize one transaction and optionally promote the merchant→category mapping to a rule. This is the endpoint behind the "Always categorize Golda as Eating out?" prompt.

- Method/path: `POST /api/v1/transactions/{id}/categorize`
- Auth: required. Ownership enforced (→ 404).
- Request schema:

```json
{
  "category_id": "c...02",
  "promote_to_rule": true,
  "match_type": "merchant_exact",
  "apply_to_existing": false
}
```
- `category_id` (required) — a consumer-layer category (else `422 not_consumer_category`).
- `promote_to_rule` (optional, default false) — when true, UPSERT a `category_rules` row with `source='user_correction'`, the given `match_type` (default `merchant_exact`), `match_value` = the transaction's merchant's `normalized_merchant_name` (for exact) or a validated fragment (for contains), and `category_id`. Requires the transaction to have a merchant (else `422 unknown_merchant`). User confirmation IS the `promote_to_rule:true` flag — the rule is never created without it.
- `match_type` (optional, default `merchant_exact`). A `merchant_contains` value that is too short/generic is rejected `422 validation_error` (MERCHANT_NORMALIZATION_SPEC §10/§12 generic-token guard).
- `apply_to_existing` (optional, default false) — when true AND a rule was promoted, also re-categorize the principal's EXISTING transactions for that merchant to `category_id`. Default false: rules apply going forward only; bulk rewrite of history is explicit and opt-in (CATEGORY_TAXONOMY §9).
- Upsert semantics: keyed on `(user_id, match_type, match_value)`. A new correction for the same merchant UPDATES the single existing rule (changes `category_id`, refreshes `updated_at`) — never stacks a rival (schema §8). Precedence at suggestion time follows the §9 ladder; `user_correction` outranks `system`.
- Response 200:

```json
{
  "transaction": { "...": "updated transaction object, category_id = c...02" },
  "rule": {
    "id": "r...01",
    "match_type": "merchant_exact",
    "match_value_present": true,
    "category_id": "c...02",
    "category_key": "eating_out",
    "source": "user_correction",
    "priority": 100,
    "is_active": true,
    "updated_at": "2026-06-14T09:20:00Z"
  },
  "applied_to_existing_count": 0
}
```
- `rule` is null when `promote_to_rule` was false. NOTE: `match_value` itself (the merchant text/fragment) is sensitive and is NOT returned verbatim — the response exposes `match_value_present: true` and the `category_id`, never the raw fragment. (The client already knows the merchant from the transaction.)
- `applied_to_existing_count` — number of existing transactions re-categorized (0 when `apply_to_existing=false`).
- Errors: `401`, `404`, `422 validation_error` (non-consumer category, missing merchant for a rule, generic contains fragment), `503`, `500`.
- Tests: categorize-only (no rule) changes one row; promote creates one rule; second promote for same merchant updates (not stacks); `apply_to_existing=true` rewrites existing and returns the count; user_correction outranks system at next suggestion.

### POST /category-rules

Create (upsert) a rule directly (e.g. from Settings > category management), independent of a specific transaction.

- Method/path: `POST /api/v1/category-rules`
- Auth: required.
- Request schema:

```json
{
  "match_type": "merchant_exact",
  "merchant_id": "m...aa",
  "match_value": null,
  "category_id": "c...02",
  "priority": 100
}
```
- `match_type` (required) — `merchant_exact` | `merchant_contains`.
- For `merchant_exact`: send `merchant_id`; the server derives `match_value` from that merchant's `normalized_merchant_name` (keeps the key canonical and avoids the client sending normalized text). For `merchant_contains`: send `match_value` (the fragment), validated against the generic-token denylist and a minimum length.
- `category_id` (required) — consumer-layer.
- `priority` (optional, default 100).
- `source` is always `user_correction` for this endpoint (system rules are seed-only, not client-creatable).
- Upsert on `(user_id, match_type, match_value)` — update-not-stack.
- Response 201 (or 200 on update): the `rule` object (same shape as above; `match_value` not echoed verbatim).
- Errors: `401`, `422 validation_error` (generic/short contains fragment, non-consumer category, unknown merchant), `409 conflict` (concurrent create race), `503`, `500`.

### PATCH /category-rules/{id}

- Method/path: `PATCH /api/v1/category-rules/{id}`
- Auth: required. Ownership enforced (→ 404).
- Request (all optional): `category_id` (consumer-layer), `priority`, `is_active`. `match_type`/`match_value` are NOT editable (changing the key is a new rule); deactivate-and-recreate instead.
- Response 200: the updated `rule`.
- Errors: `401`, `404`, `422`, `503`, `500`.

(No GET /category-rules list is required by Quick Add or Home; rules are applied server-side during suggestion. A management list can be added additively if Settings needs it — not in the minimal v0.0.1 surface. Assumption: omitted to keep the surface small; add later if the category-management screen ships.)

---

## 11. Merchant alias confirmation

### POST /merchants/{id}/aliases

Confirm that a typed/variant form is the SAME merchant — the "Same as existing merchant?" / cross-script "Same as Golda?" action. Creates a `user_confirmed` alias. There is NO silent merge for low confidence; this explicit, user-driven endpoint is the only way a cross-script link is created.

- Method/path: `POST /api/v1/merchants/{id}/aliases` — `{id}` is the merchant the alias resolves TO (the existing "Golda").
- Auth: required. Ownership of `{id}` enforced (→ 404).
- Request schema:

```json
{
  "alias_text": "גולדה",
  "absorb_merchant_id": "m...bb"
}
```
- `alias_text` (required) — the verbatim variant form. The server normalizes it to `normalized_alias_key` (MERCHANT_NORMALIZATION_SPEC §4). Sensitive; never logged.
- `absorb_merchant_id` (optional) — when the variant had already become its own merchant (e.g. Quick Add created a separate "גולדה" merchant, then the user confirms "Same as Golda?"), this names that other merchant so the server links its alias key to `{id}` and (assumption, recommended) re-points that merchant's transactions to `{id}` then removes the now-redundant merchant. Omitted when the alias is purely a new typed variant.
- `source` is always `user_confirmed` for this endpoint (the user explicitly confirmed). `confidence` is recorded as a user-confirmed trust marker.
- Constraint: `UNIQUE(user_id, normalized_alias_key)` — an alias key resolves to exactly one merchant. If the key already resolves to a DIFFERENT merchant, return `409 conflict` (the client must resolve which merchant is canonical) rather than silently re-pointing.
- No silent merge: this endpoint is the ONLY path that links cross-script/variant forms. The system never creates a `user_confirmed` alias on its own; `system_suggested`/`import_parsed` aliases (low/medium trust) never cause a merge (schema §6).
- Response 201:

```json
{
  "alias": {
    "id": "a...01",
    "merchant_id": "m...aa",
    "source": "user_confirmed",
    "confidence": "user_confirmed",
    "created_at": "2026-06-14T09:25:00Z",
    "last_seen_at": null
  },
  "absorbed_merchant_id": "m...bb",
  "repointed_transaction_count": 2
}
```
- `alias.alias_text`/`normalized_alias_key` are NOT echoed verbatim (sensitive). The client already knows the text it sent.
- `absorbed_merchant_id` / `repointed_transaction_count` present only when `absorb_merchant_id` was supplied.
- After this, a future typed "גולדה" resolves at `alias_exact` and auto-selects "Golda", and Golda's `merchant_exact` rule fires for it (schema §6/§8).
- Errors: `401`, `404` (merchant `{id}` missing/not owned), `409 conflict` (alias key already resolves to another merchant), `422 validation_error`, `503`, `500`.
- Tests: confirming an alias makes the variant auto-select thereafter; absorbing a duplicate merchant re-points its transactions and returns the count; a key already pointing elsewhere → 409; no `user_confirmed` alias is ever created without this call; alias text never logged.

---

## 12. Recurring expense template endpoints

CRUD for `recurring_expense_templates`. PROJECTION-ONLY: no endpoint here ever creates a `transactions` row. Templates contribute to "Upcoming commitments" on Home (section 13).

### GET /recurring-templates

- Method/path: `GET /api/v1/recurring-templates?active=<bool>`
- Auth: required. Principal-scoped.
- Query: `active` (optional) — filter by `is_active`. Omitted → all.
- Response 200:

```json
{
  "items": [
    {
      "id": "rt...01",
      "name": "Gym",
      "amount_minor": -12000,
      "currency": "ILS",
      "category_id": "c...08",
      "category_key": "health",
      "merchant_id": null,
      "cadence": "monthly",
      "next_expected_date": "2026-06-20",
      "counts_in_projection": true,
      "is_active": true,
      "note": null,
      "created_at": "2026-06-01T07:00:00Z",
      "updated_at": "2026-06-01T07:00:00Z"
    }
  ]
}
```
- `amount_minor` is the projection amount in agorot. (Sign mirrors an expense by convention; the projection sum uses magnitude — section 13.)

### POST /recurring-templates

- Method/path: `POST /api/v1/recurring-templates`
- Auth: required.
- Request schema:

```json
{
  "name": "Netflix",
  "amount": "45.90",
  "category_id": "c...07",
  "merchant_id": null,
  "cadence": "monthly",
  "next_expected_date": "2026-07-05",
  "counts_in_projection": true,
  "note": null,
  "currency": "ILS"
}
```
- `name` (required) — sensitive; never logged.
- `amount` (required) — major units, normalized to agorot (section 14).
- `category_id` (required) — a consumer-layer category reused for grouping (CATEGORY_TAXONOMY §5); `bank_movement` → `422 not_consumer_category`. (Schema: `category_id` is NOT NULL on templates.)
- `merchant_id` (optional).
- `cadence` (required) — `weekly` | `monthly` | `yearly`.
- `next_expected_date` (required) — `YYYY-MM-DD`.
- `counts_in_projection` (optional, default true), `is_active` defaults true on create.
- `note` (optional) — sensitive; never logged.
- Response 201: the created template object.
- Firm: creates NO transaction. A test asserts the principal's `transactions` count is unchanged after this call.
- Errors: `401`, `422 validation_error`, `503`, `500`.

### PATCH /recurring-templates/{id}

- Method/path: `PATCH /api/v1/recurring-templates/{id}`
- Auth: required. Ownership enforced (→ 404).
- Request (all optional): `name`, `amount`, `category_id` (consumer-layer), `merchant_id`, `cadence`, `next_expected_date`, `counts_in_projection`, `is_active`, `note`.
- Use cases: change the amount (projection follows — CATEGORY_TAXONOMY §5), exclude from projection (`counts_in_projection:false`) without deleting, or deactivate (`is_active:false`).
- Response 200: the updated template.
- Errors: `401`, `404`, `422`, `503`, `500`.

### Deactivate vs delete

- Recommendation (firm): SOFT deactivate via `PATCH … {"is_active": false}` is the primary "stop this commitment" action — it stops the template projecting while keeping it for history (CATEGORY_TAXONOMY §5; schema §3.7). This is preferred for a cancelled subscription.
- A hard delete is ALSO offered for a template created in error: `DELETE /api/v1/recurring-templates/{id}` → `204`. Justification: deactivate preserves a real cancelled commitment for the record; hard delete removes a genuine mistake. Both are simple in a single-user tool; `category_id` uses `ON DELETE RESTRICT` in the schema but since the FK target (a system category) is never deleted, the template delete is unaffected.
- Errors (DELETE): `401`, `404`, `503`, `500`.
- Tests: create projects but writes no transaction; deactivate removes it from projection but keeps the row; delete removes it; amount edit changes projection.

---

## 13. Home dashboard endpoint

### GET /home

One call returns everything Home shows, with actuals and projection ALWAYS as separate fields.

- Method/path: `GET /api/v1/home?month=YYYY-MM`
- Auth: required. Principal-scoped.
- Query: `month` (optional, default the server's current month) — `YYYY-MM`.
- Response 200:

```json
{
  "month": "2026-06",
  "currency": "ILS",
  "spent_so_far_minor": 214000,
  "top_category": {
    "category_id": "c...01",
    "category_key": "groceries",
    "label_en": "Groceries",
    "total_minor": 78000
  },
  "category_totals": [
    { "category_id": "c...01", "category_key": "groceries", "label_en": "Groceries", "total_minor": 78000 },
    { "category_id": "c...02", "category_key": "eating_out", "label_en": "Eating out", "total_minor": 51000 }
  ],
  "recent_transactions": [
    { "id": "t...f1", "amount_minor": -3300, "currency": "ILS",
      "merchant_display_name": "Golda", "category_key": "eating_out",
      "occurred_on": "2026-06-14", "is_uncategorized": false },
    { "id": "t...e0", "amount_minor": -5000, "currency": "ILS",
      "merchant_display_name": null, "category_key": null,
      "occurred_on": "2026-06-14", "is_uncategorized": true }
  ],
  "uncategorized_count": 1,
  "upcoming_commitments": [
    { "template_id": "rt...01", "name_present": true, "category_key": "health",
      "amount_minor": -12000, "next_expected_date": "2026-06-20" }
  ],
  "committed_amount_minor": 130000,
  "known_this_month": {
    "spent_actual_minor": 214000,
    "committed_projected_minor": 130000
  },
  "warnings": []
}
```

Field semantics (all amounts agorot; `_minor` suffix denotes integer agorot):
- `spent_so_far_minor` — the ACTUAL spend headline (Layer A). Computed as the magnitude sum over `transactions` where `source='manual'` AND `transaction_type='expense'` AND `is_card_settlement=false` AND `occurred_on` in `month` AND (`category_id IS NULL` OR the category's `included_in_actual_spending=true`). Uncategorized expenses DO count (schema §10 query 1). Returned as a non-negative integer (magnitude).
- `top_category` — the single largest Layer A category this month (schema §10 query 2); uncategorized excluded from the ranking. `null` if no categorized spend yet.
- `category_totals` — per-category Layer A magnitude totals for the month, ranked DESC; uncategorized excluded (it is not a category). Drives the category drill-down.
- `recent_transactions` — the last few entries (schema §10 query 3), uncategorized rows flagged with `is_uncategorized: true`. Money in agorot.
- `uncategorized_count` — count of `category_id IS NULL` rows for the "needs a category" review (schema §10 query 4).
- `upcoming_commitments` — the forward-looking list of active, projecting templates due in the month (schema §10 query 5). `name_present` is a boolean placeholder — the template name is sensitive; the client fetches names via `GET /recurring-templates` where it renders the management list, while Home shows amounts/dates. (Assumption: Home avoids echoing template names in the dashboard payload to minimize sensitive content on a frequently-fetched endpoint; if the client needs names on Home, it joins from the templates list it already holds. This is a privacy-minimizing default, adjustable if the UX requires names inline.)
- `committed_amount_minor` — the PROJECTED commitment total (Layer B): magnitude sum of `amount_minor` over active templates with `counts_in_projection=true` and `next_expected_date` in the month. Returned as a non-negative integer (magnitude).
- `known_this_month` — the clearly-LABELED-SEPARATE object holding `spent_actual_minor` and `committed_projected_minor` as DISTINCT fields. There is intentionally NO single blended total anywhere in this response. The client renders "Spent ₪2,140 · Committed ₪1,300", never one ambiguous number (firm rule; CATEGORY_TAXONOMY §12; MANUAL_FIRST_MVP_REVISION §10).
- `warnings` — optional non-blocking dashboard notes (e.g. `{ code: "many_uncategorized", message: "Some items need a category." }`), never errors.
- Note: Layer C (bank cash-flow) is ABSENT in pure-manual v0.0.1 — no `cash_flow` field appears until bank import lands (v0.0.2), at which point it is a separate labelled object with card settlements excluded from spend.
- Errors: `401`, `422` (bad `month`), `503`, `500`.
- Tests: a ₪33 expense + a ₪120 active template returns `spent_actual_minor=3300` and `committed_projected_minor=12000` as separate fields, with NO field equal to 15300 (never blended); uncategorized expense counts in `spent_so_far_minor` but not in `top_category`/`category_totals`; settlement rows (future) excluded by construction.

---

## 14. Data normalization rules at the API boundary

The contract accepts user-friendly input and normalizes deterministically to the frozen storage shapes. All normalization happens server-side.

Decimal amount input → `amount_minor`:
- Accept a JSON number or decimal string in MAJOR units (shekels). Parse to a fixed-point decimal (never binary float) to avoid rounding error.
- Round/precision: at most 2 decimal places. MORE than 2 decimal places is REJECTED `422 too_many_decimals` (never silently rounded — silent rounding would misstate money). Exactly 0–2 places allowed; `33` → 3300 agorot, `33.5` → 3350, `33.50` → 3350.
- Zero is REJECTED `422 zero_amount` (a zero movement is invalid; schema `CHECK (amount_minor <> 0)`; QUICK_ADD_UX_SPEC §5).
- Negative input is REJECTED for an `expense` (`422 negative_amount`); the client never sends a minus sign. "Money back" is `transaction_type=income`/`refund`, entered via the explicit toggle, not a negative amount.
- Sign applied server-side from `transaction_type` (schema §5 convention): `expense` → stored NEGATIVE agorot; `income`/`refund` → stored POSITIVE; `adjustment` → sign per the correction's intent (assumption: explicit signed `adjustment` is a future/edge path; v0.0.1 mainly produces `expense`). The client always sends a non-negative magnitude; the server owns the sign. This guarantees the stored sign and the displayed positive spend never conflict.
- Currency: default the user's `base_currency` (`ILS`); validate ISO-4217 length 3 (`422 invalid_currency` otherwise). v0.0.1 does not convert currencies.

Merchant raw input handling:
- Preserve the verbatim typed text as `transactions.raw_merchant_input` (after only invisible/bidi strip + NFC, MERCHANT_NORMALIZATION_SPEC §4 steps 3–4). Never altered for display.
- Compute `normalized_merchant_name` via the deterministic pipeline (MERCHANT_NORMALIZATION_SPEC §4): trim, collapse whitespace, strip invisible/bidi, NFC, case-fold Latin (Hebrew preserved), canonicalize safe punctuation. This is the matching key, never shown.
- Lookup/create: resolve against the principal's merchants/aliases via the confidence ladder. `exact`/`alias_exact`/`normalized_exact` (same-script) reuse the existing merchant; `none` CREATES a new merchant and stores the raw input as its first alias. Cross-script/`contains` NEVER auto-merges — it creates a separate merchant and surfaces an `alias_suggestion` (sections 7, 8, 11). No fuzzy auto-merge; `fuzzy_possible` behaves as `none`.

Category validation:
- A `category_id` on a transaction, categorize, rule, or template MUST be a system category (`user_id IS NULL`) or owned by the same principal (schema §13 same-user-or-system). Foreign-owned → `404`/`422 unknown_category`.
- Quick Add and categorize accept ONLY `layer == consumer_spending` categories (the 14). A `bank_movement` category in manual entry → `422 not_consumer_category`. The client also filters the picker to consumer categories (section 6), but the server enforces it independently.

Date defaulting:
- `occurred_on` defaults to the server's current date (today) when omitted/null (schema `DEFAULT CURRENT_DATE`; QUICK_ADD_UX_SPEC §5). Backdating is allowed freely; a date more than ~1 day in the future is rejected `422 invalid_date` (typo guard; assumption).

Note handling:
- Stored verbatim in `transactions.note` (or `recurring_expense_templates.note`). NEVER logged, NEVER embedded, treated as highly sensitive free text (section 15).

Privacy rules at the boundary: no normalization step ever logs the raw input, the normalized key, the amount, or the note — only the resulting `confidence` enum and whether a merchant/category resolved (section 15).

---

## 15. Privacy and logging

Quick Add and Home handle the most sensitive data in the app — where and how much someone spends. The logging rules are absolute (PRD §15; MERCHANT_NORMALIZATION_SPEC §14; QUICK_ADD_UX_SPEC §15; DATABASE_SCHEMA §11).

MUST NEVER be logged (in any request log, response log, error log, or trace):
- Merchant text: `merchant_input`, `raw_merchant_input`, any `alias_text`, `normalized_merchant_name`/`normalized_alias_key`, and `display_name`.
- Amounts: the input `amount`, `amount_minor` (in any unit), and any combination that re-identifies a purchase.
- Note: `transactions.note` and `recurring_expense_templates.note` (free text — may contain anything).
- Raw input: any verbatim typed field.
- Correction content: a `category_rules.match_value` and the category text WHEN paired with an amount or merchant.
- Identity: `users.email`, `credential_ref`, and the dev token.

SAFE to log (structured: IDs / counts / enums / duration buckets only):
- `request_id`, `endpoint` name, HTTP `status` code.
- Opaque IDs only: `user_id` (the uuid, never the email), `transaction_id`, `merchant_id`, `alias_id`, `category_id`, `rule_id`, `template_id`.
- `validation_error_code` enum (e.g. `empty_amount`, `zero_amount`, `too_many_decimals`, `not_consumer_category`).
- `confidence_level` enum (`exact`|`alias_exact`|`normalized_exact`|`recent_suggestion`|`contains`|`fuzzy_possible`|`none`) — the name only, never the text that produced it.
- Other enum names: `transaction_type`, `source`, `match_type`, rule `source`, `cadence`.
- Row counts (items returned, `applied_to_existing_count`, `uncategorized_count`) and `duration_bucket` (`<2s`|`2-5s`|`>5s`) to verify the five-second goal.

Standard safe log line shape: `{ request_id, endpoint, status, duration_bucket, validation_error_code?, confidence_level?, row_count? }`.

How to debug safely without PII: trace by `request_id` + IDs + confidence enum. Example: "req_7f3a9c20 quick-add 201 <2s confidence=normalized_exact merchant_id=m…aa rule_prompt=offered" — enough to reproduce a wrong match without ever logging the merchant text or amount. If a developer must inspect the actual text, they read it from SQL as the data owner in a controlled context, never from logs. Every error `message` is generic and content-free (section 5) so even error logs leak nothing. This is enforced as a review rule on every log statement and every error string.

---

## 16. Deferred endpoints (explicitly NOT in v0.0.1)

The following are intentionally absent from the active contract. They are listed so the surface stays small and the v0.0.2+ author has a target. None has a live route in v0.0.1; calling a stub returns `403 unsupported_operation` (or simply does not exist).

- AI coach chat — `POST /coach/messages`, conversation/message endpoints. Deferred to v0.1 (MANUAL_FIRST_MVP_REVISION §5; PRD Phase 5). No `ai_conversations`/`ai_chat_messages` tables in v0.0.1.
- RAG / embeddings — any retrieval or embedding endpoint. Deferred to v0.1. Raw transactions are NEVER embedded (firm invariant); pgvector may be installed but unused.
- Bank cash-flow import — `POST /imports/bank/preview`, `POST /imports/bank/commit` (clearly marked DEFERRED to v0.0.2). The import pipeline (IMPORT_PIPELINE_SPEC) is valid but NOT wired now; `accounts`/`import_batches` are retained-but-deferred tables, not exposed by any v0.0.1 route. Settlement rows will set `is_card_settlement=true` and be excluded from spend by the existing Home query.
- Itemized card import — `POST /imports/card/*`. Deferred to v0.0.3.
- Insights — `GET /insights`. Deferred to v0.1 (needs summaries/detection).
- Monthly summaries — `GET /summaries/{month}`. Deferred to v0.1; v0.0.1 computes month totals live from `transactions` (Home), with no stored summary that could drift from actuals.
- Open banking / live sync — deferred indefinitely (PRD §6).
- Push notifications — no endpoints; deferred (PRD §6; MANUAL_FIRST_MVP_REVISION §12).
- Public auth / sign-up / billing — no registration, OAuth, sessions UI, or subscription endpoints. v0.0.1 is single-user local (section 3).

---

## 17. API examples (consolidated)

Concrete JSON for the core flows. Money in agorot on output; decimal major units on input; dates `YYYY-MM-DD`; timestamps RFC 3339 UTC.

GET /categories (excerpt — 22 rows total):
```json
{ "items": [
  { "id": "c...01", "key": "groceries", "label_en": "Groceries", "label_he": "קניות מזון / סופר",
    "layer": "consumer_spending", "included_in_actual_spending": true, "included_in_cash_flow": false, "is_system": true },
  { "id": "c...20", "key": "interest_bank_fee", "label_en": "Interest / bank fee", "label_he": "ריבית / עמלה",
    "layer": "bank_movement", "included_in_actual_spending": false, "included_in_cash_flow": true, "is_system": true }
] }
```

GET /merchants/suggestions?query=gol:
```json
{ "query_confidence": "recent_suggestion", "auto_select_merchant_id": null,
  "items": [ { "merchant_id": "m...aa", "display_name": "Golda", "confidence": "recent_suggestion",
      "requires_confirmation": false, "matched_via": "merchant",
      "suggested_category_id": "c...02", "suggested_category_key": "eating_out",
      "suggested_category_source": "recent_memory" } ] }
```

POST /transactions/quick-add (amount-only):
```json
// request:  { "amount": 33 }
// response 201:
{ "transaction": { "id": "t...f1", "amount_minor": -3300, "currency": "ILS",
    "transaction_type": "expense", "source": "manual", "merchant_id": null,
    "merchant_display_name": null, "category_id": null, "category_key": null,
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T08:31:05Z", "updated_at": "2026-06-14T08:31:05Z" },
  "warnings": [], "category_suggestion": null, "rule_prompt": { "offer": false }, "alias_suggestion": null }
```

POST /transactions/quick-add (full, Mode C):
```json
// request:  { "amount": "33.50", "merchant_id": "m...aa", "category_id": "c...02" }
// response 201:
{ "transaction": { "id": "t...f4", "amount_minor": -3350, "currency": "ILS",
    "transaction_type": "expense", "source": "manual", "merchant_id": "m...aa",
    "merchant_display_name": "Golda", "category_id": "c...02", "category_key": "eating_out",
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T08:33:00Z", "updated_at": "2026-06-14T08:33:00Z" },
  "warnings": [],
  "category_suggestion": { "category_id": "c...02", "category_key": "eating_out", "source": "user_choice" },
  "rule_prompt": { "offer": true, "merchant_id": "m...aa",
    "suggested_category_id": "c...02", "suggested_category_key": "eating_out" },
  "alias_suggestion": null }
```

PATCH /transactions/{id} (category correction):
```json
// request:  { "category_id": "c...05" }
// response 200:
{ "transaction": { "id": "t...f1", "amount_minor": -3300, "currency": "ILS",
    "transaction_type": "expense", "source": "manual", "merchant_id": "m...aa",
    "merchant_display_name": "Golda", "category_id": "c...05", "category_key": "shopping",
    "occurred_on": "2026-06-14", "note": null, "is_card_settlement": false,
    "created_at": "2026-06-14T08:31:05Z", "updated_at": "2026-06-14T10:00:00Z" },
  "rule_prompt": { "offer": true, "merchant_id": "m...aa",
    "suggested_category_id": "c...05", "suggested_category_key": "shopping" } }
```

POST /transactions/{id}/categorize (promote to rule):
```json
// request:  { "category_id": "c...02", "promote_to_rule": true, "match_type": "merchant_exact", "apply_to_existing": false }
// response 200:
{ "transaction": { "id": "t...f1", "category_id": "c...02", "category_key": "eating_out", "...": "..." },
  "rule": { "id": "r...01", "match_type": "merchant_exact", "match_value_present": true,
    "category_id": "c...02", "category_key": "eating_out", "source": "user_correction",
    "priority": 100, "is_active": true, "updated_at": "2026-06-14T10:05:00Z" },
  "applied_to_existing_count": 0 }
```

POST /category-rules (direct upsert):
```json
// request:  { "match_type": "merchant_exact", "merchant_id": "m...aa", "category_id": "c...02", "priority": 100 }
// response 201:
{ "rule": { "id": "r...01", "match_type": "merchant_exact", "match_value_present": true,
    "category_id": "c...02", "category_key": "eating_out", "source": "user_correction",
    "priority": 100, "is_active": true, "updated_at": "2026-06-14T10:06:00Z" } }
```

POST /merchants/{id}/aliases (cross-script confirm):
```json
// request:  { "alias_text": "גולדה" }     (id = m...aa, the existing "Golda")
// response 201:
{ "alias": { "id": "a...01", "merchant_id": "m...aa", "source": "user_confirmed",
    "confidence": "user_confirmed", "created_at": "2026-06-14T10:10:00Z", "last_seen_at": null },
  "absorbed_merchant_id": null, "repointed_transaction_count": 0 }
```

POST /recurring-templates (projection-only):
```json
// request:  { "name": "Netflix", "amount": "45.90", "category_id": "c...07",
//             "cadence": "monthly", "next_expected_date": "2026-07-05", "counts_in_projection": true }
// response 201:
{ "id": "rt...02", "name": "Netflix", "amount_minor": -4590, "currency": "ILS",
  "category_id": "c...07", "category_key": "subscriptions", "merchant_id": null,
  "cadence": "monthly", "next_expected_date": "2026-07-05",
  "counts_in_projection": true, "is_active": true, "note": null,
  "created_at": "2026-06-14T10:12:00Z", "updated_at": "2026-06-14T10:12:00Z" }
// NOTE: the principal's transactions count is UNCHANGED by this call.
```

GET /home?month=2026-06:
```json
{ "month": "2026-06", "currency": "ILS",
  "spent_so_far_minor": 214000,
  "top_category": { "category_id": "c...01", "category_key": "groceries", "label_en": "Groceries", "total_minor": 78000 },
  "category_totals": [
    { "category_id": "c...01", "category_key": "groceries", "label_en": "Groceries", "total_minor": 78000 },
    { "category_id": "c...02", "category_key": "eating_out", "label_en": "Eating out", "total_minor": 51000 } ],
  "recent_transactions": [
    { "id": "t...f1", "amount_minor": -3300, "currency": "ILS", "merchant_display_name": "Golda",
      "category_key": "eating_out", "occurred_on": "2026-06-14", "is_uncategorized": false } ],
  "uncategorized_count": 1,
  "upcoming_commitments": [
    { "template_id": "rt...01", "name_present": true, "category_key": "health",
      "amount_minor": -12000, "next_expected_date": "2026-06-20" } ],
  "committed_amount_minor": 130000,
  "known_this_month": { "spent_actual_minor": 214000, "committed_projected_minor": 130000 },
  "warnings": [] }
```

---

## 18. Acceptance criteria

This contract is complete when ALL hold:
1. Supports every Quick Add flow: amount-only, amount+merchant, amount+merchant+category, each via `POST /transactions/quick-add` returning 201 without enrichment ever blocking the save.
2. Amount-only is first-class: a request with only `amount` persists `merchant_id=null`, `category_id=null`, `occurred_on=today`, `source=manual`, and the row counts in `spent_so_far_minor`.
3. Merchant autocomplete + category suggestion: `GET /merchants/suggestions` and `GET /merchants/recent` return ranked candidates with `confidence`, `requires_confirmation`, and a pre-resolved category suggestion via the precedence ladder; `exact`/`alias_exact`/`normalized_exact` auto-select, others suggest, none auto-merge.
4. User-confirmed aliases: `POST /merchants/{id}/aliases` is the only path that links cross-script/variant forms, always `source=user_confirmed`, with no silent merge and a 409 when a key already resolves elsewhere.
5. Category rules: `POST /transactions/{id}/categorize` and `POST /category-rules` upsert on `(user_id, match_type, match_value)` (update-not-stack), `source=user_correction`, user-confirmed, going-forward by default with explicit `apply_to_existing`.
6. Recurring projected commitments: `recurring-templates` CRUD creates/reads/updates/deactivates templates and provably creates NO transaction row.
7. Home actuals and commitments separate: `GET /home` returns `spent_so_far_minor` and `committed_amount_minor` / `known_this_month.{spent_actual_minor, committed_projected_minor}` as distinct fields, with no blended total anywhere.
8. Matches the frozen schema: every field, enum, default, nullable, and money unit maps to DATABASE_SCHEMA_V0_0_1.md (signed agorot, ILS default, date-only `occurred_on`, UTC metadata, canonical category keys, `transaction_type`/`source`/`cadence`/alias-`source`/rule-`match_type` enums).
9. Avoids overbuild: no AI/RAG, no bank/card import, no insights/summaries, no public-SaaS auth in the active surface; deferred items are clearly marked (section 16) and use no deferred table.
10. Privacy holds: no endpoint logs merchant text, amount, note, raw input, or correction content; safe logs carry only request id, endpoint, status, duration bucket, validation error code, confidence-level enum, and row counts; error messages are generic; ownership mismatch is 404.
11. Ready for implementation: every endpoint has method, path, request schema, response schema, status codes, validation rules, error states, and tests, written against frozen entities — a backend engineer can implement without further product decisions.

---

## 19. Next recommended prompt

Firm recommendation: proceed to docs/QA_TEST_PLAN_V0_0_1.md next — do the QA test plan BEFORE starting implementation.

Justification: the build-filter sequence (MANUAL_FIRST_MVP_REVISION §13 lists QA_TEST_PLAN_V0_0_1.md as a planning artifact) and the nature of this product both point to QA-plan-first, and it MATERIALLY de-risks implementation rather than being ceremony. The reasons are concrete and specific to v0.0.1:
- The hardest correctness rules in this app are testable invariants that are cheap to get wrong and expensive to discover late: recurring templates must create ZERO transactions (double-counting guard), Home must NEVER blend actual and projected, money must round to agorot with >2-decimals rejected (never silently rounded), cross-script merchants must never silently merge, the rule upsert must update-not-stack, ownership mismatch must be 404-not-403, and NO sensitive content may appear in logs. These are exactly the things a written test plan pins down as pass/fail cases before code exists, so the implementation is built to satisfy them rather than retrofitted.
- The schema and this API contract already embed test cases (schema §15, this doc's per-endpoint Tests). A QA plan consolidates them into one acceptance matrix spanning Quick Add speed/correctness, the precedence ladder, projection math, actuals-vs-projection separation, and the privacy/no-PII-in-logs assertions — the precise re-scope MANUAL_FIRST_MVP_REVISION §13 calls for. Writing the FastAPI skeleton first would mean building endpoints without an agreed acceptance bar for these subtle, money-and-privacy-critical behaviors.
- The QA plan is the last cheap place to catch a contract gap. If the test plan reveals an untestable or ambiguous endpoint behavior, fixing the contract on paper is far cheaper than after the skeleton and migrations are written.

I considered recommending starting implementation (repo setup, FastAPI skeleton, Postgres connection, v0.0.1 migrations, seed categories, health endpoint) immediately and reject it as premature ONLY by a short margin: the schema and contract are frozen enough that the skeleton is low-risk. But the asymmetry favors the QA plan — it is the final planning artifact, it directly hardens the money/privacy/double-counting invariants that define correctness here, and it costs little. Once the QA plan is approved, implementation should begin immediately and can proceed quickly because the acceptance bar will be unambiguous.

Exact next prompt to send after approving this contract:

> "Acting as the qa-tester agent with the product-architect and backend-api-engineer agents, and using docs/PRD_V0_1.md as the long-term vision, docs/MANUAL_FIRST_MVP_REVISION.md as the governing v0.0.1 decision, docs/CATEGORY_TAXONOMY.md, docs/MERCHANT_NORMALIZATION_SPEC.md, docs/QUICK_ADD_UX_SPEC.md, docs/DATABASE_SCHEMA_V0_0_1.md (frozen schema), and docs/API_CONTRACT_V0_0_1.md (the API contract) as the sources of truth, produce docs/QA_TEST_PLAN_V0_0_1.md for manual-first v0.0.1. Define the acceptance test matrix as concrete pass/fail cases covering: Quick Add speed and correctness (amount-only, amount+merchant, amount+merchant+category; merchant/category optional; default-today date; save-first never blocked); the firm rule that recurring templates create ZERO transactions; actuals-vs-projection separation on Home (no blended total; spent_actual vs committed_projected as distinct fields); money normalization (decimal-to-agorot, reject >2 decimals, reject zero/negative expense, signed-by-type, ILS default); merchant matching (exact/alias_exact/normalized_exact auto-select; recent_suggestion/contains suggest; cross-script and fuzzy NEVER silently merge; user-confirmed aliases only); category suggestion precedence ladder; category-rule upsert update-not-stack with user_correction authoritative and explicit opt-in bulk apply; ownership mismatch returns 404 not 403; and the privacy invariant that no request/response/error/log ever contains merchant text, amount, note, raw input, or correction content (only IDs/counts/enums/duration buckets). Map every test to the API endpoint and the schema constraint it exercises, and mark which are blocking for v0.0.1 ship. Planning and specification only — no test code, no implementation."

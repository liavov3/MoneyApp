# Money App — Database Schema (v0.0.1, manual-first)

Status: Schema specification only. No migrations, no application code, no API endpoints, no UI. This document defines the concrete PostgreSQL data model that v0.0.1 freezes for the manual-first build.
Owner: database-engineer (lead), with product-architect, backend-api-engineer, security-privacy-engineer, and qa-tester perspectives.
Governing decision: docs/MANUAL_FIRST_MVP_REVISION.md (2026-06-14) — v0.0.1 is manual-first; fast Quick Add is the primary loop. This supersedes the import-first v0.0.1 scope in docs/MVP_EXECUTION_ALIGNMENT.md.
Inputs (all read): docs/PRD_V0_1.md, docs/MANUAL_FIRST_MVP_REVISION.md (esp. §9 data model impact), docs/CATEGORY_TAXONOMY.md (esp. §10 seed table), docs/MERCHANT_NORMALIZATION_SPEC.md (esp. §13 data model implications), docs/QUICK_ADD_UX_SPEC.md (the settled interaction model), docs/IMPORT_PIPELINE_SPEC.md (future-compatibility fields).
Firm invariants carried forward unchanged: PostgreSQL; money is signed integer minor units (agorot) + currency code (ILS default); UTC `timestamptz` for metadata timestamps; financial/occurred dates stored as `date` (date-only); `user_id` on every user-owned table; raw merchant input and notes are sensitive PII and are NEVER logged; raw transactions live in SQL ONLY and are NEVER embedded; design is ADDITIVE for future expansion (bank import, card import, MonthlySummary, AI/RAG) — never a rewrite; recurring templates are PROJECTION-ONLY and create NO transaction rows in v0.0.1; the `is_card_settlement` exclusion flag is carried for future imports.
Anything labelled "assumption" is an implementation judgement by the author, not an established upstream fact.
Date: 2026-06-14

---

## 1. Purpose

This schema is the persisted data model for manual-first v0.0.1. It supports exactly the loop the manual-first revision defines: the founder logs a purchase in under five seconds via Quick Add (amount required; merchant and category optional), category memory improves as they correct, and Home shows month-to-date actual spending and recurring commitments as two clearly separate numbers.

What this schema SUPPORTS in v0.0.1:
- Amount-only transactions (a valid expense with no merchant and no category), per QUICK_ADD_UX_SPEC §3 Mode A.
- Optional merchant and optional category on every transaction (`merchant_id` and `category_id` both nullable; "uncategorized" is a first-class state, not a fake "Other").
- A stable, normalized merchant identity with first-class aliases that collapse variant/cross-script spellings into one payee only on user confirmation (MERCHANT_NORMALIZATION_SPEC §13).
- Category memory and learning via CategoryRule, with user corrections outranking system rules (CATEGORY_TAXONOMY §9).
- The 14 consumer-spending categories AND the 8 bank-movement categories, seeded now as stable system rows (CATEGORY_TAXONOMY §10).
- Manual recurring expense templates that PROJECT future commitments and create NO transaction rows (MANUAL_FIRST_MVP_REVISION §7).
- The Home dashboard rollups: "Spent so far" (actual), "Upcoming commitments" (projected), kept always separate (CATEGORY_TAXONOMY §12).
- Signed integer minor units (agorot), ILS default, UTC metadata timestamps, date-only occurred dates, and `user_id` isolation on every user-owned row.

What this schema INTENTIONALLY DEFERS (carried as additive, never a rewrite):
- Bank cash-flow import and itemized card import (v0.0.2 / v0.0.3). The transactions table already carries every nullable import field (`account_id`, `import_batch_id`, `raw_description`, `value_date`, `reference`, `operation_type`, `is_card_settlement`, `dedup_hash`) so imports slot in without altering the table shape.
- The `accounts` and `import_batches` tables themselves (retained-but-deferred; section 4).
- MonthlySummary, recurring DETECTION, insights, AI chat, financial-knowledge documents, and pgvector embeddings (section 4). pgvector may be installed, but zero vectors are created in v0.0.1.

The design discipline: every deferred capability has its hook present (a nullable column, a stable enum value, or a documented additive table) so v0.0.2+ adds tables and activates columns without ever rewriting `transactions`.

---

## 2. Schema principles

1. Manual-first. The dominant rows are manual transactions. `source` defaults to `manual`; import sources are valid enum values but inactive in v0.0.1.
2. Amount-only transactions are supported. The only hard requirement to persist an expense is a non-zero `amount_minor`. `merchant_id` and `category_id` are nullable; nothing else blocks a save.
3. Merchant and category are optional. Uncategorized (`category_id IS NULL`) and merchant-less (`merchant_id IS NULL`) are first-class, correctable states — never coerced into "Other" (CATEGORY_TAXONOMY §8).
4. Recurring templates are projected commitments, not actual transactions. `recurring_expense_templates` rows produce projection numbers only. They create NO `transactions` rows in v0.0.1 (MANUAL_FIRST_MVP_REVISION §7). This is the single most important double-counting guard in the manual-first design.
5. Three money-meanings stay separated. Consumer spending (Layer A, from manual transactions), recurring commitments (Layer B, from templates), and bank cash-flow (Layer C, future imports) are never summed into one ambiguous number. The separation is carried by `transactions.source`, by templates being a distinct table, and by per-category flags (`included_in_actual_spending`, `included_in_cash_flow`).
6. Money is signed integer minor units. `amount_minor bigint` in agorot, plus a `currency` code (ILS default). No floating point anywhere for money. A debit/expense is negative or positive-with-explicit-type per the convention fixed in section 5.
7. `user_id` isolation everywhere. Every user-owned row carries `user_id`. Every query filters by it. System categories are the sole rows with `user_id IS NULL` (shared, read-only seed data). Multi-user-safe by construction even with one user.
8. Privacy-first logging. Raw merchant input, alias text, normalized keys, display names, notes, and amounts are sensitive and never logged. Only IDs, counts, and enum level names are loggable (section 11).
9. Future imports are additive, not a rewrite. The transactions table carries all import fields as nullable now. Activating bank import (v0.0.2) and card import (v0.0.3) means creating `accounts`/`import_batches` and populating already-present columns — never an ALTER that reshapes existing rows.

---

## 3. Tables included in v0.0.1

Seven tables are created and actively used in v0.0.1: `users`, `transactions`, `merchants`, `merchant_aliases`, `categories`, `category_rules`, `recurring_expense_templates`. (Two further tables, `accounts` and `import_batches`, are retained-but-deferred and described in section 4; they may be created at schema-install time as empty, or deferred to the v0.0.2 migration — assumption: create them empty now so the FK targets exist and the v0.0.2 migration is pure data activation. Either choice is additive.)

Conventions used in every table below:
- Primary keys are `uuid` (assumption: `gen_random_uuid()` via pgcrypto/pgcrypto-equivalent; UUIDs avoid cross-environment id collisions and never leak a sequential count). Stable for the row's lifetime.
- `created_at` / `updated_at` are `timestamptz` in UTC, default `now()`. `updated_at` is maintained by the application (or a trigger; assumption: application-maintained in v0.0.1 to avoid trigger machinery).
- All money is `bigint amount_minor` + `text currency`.
- All financial/occurred dates are `date`.
- Enumerated fields are modeled as `text` + a `CHECK` constraint (not native Postgres `enum` types) so new values are added by editing a constraint, not by `ALTER TYPE`. (Assumption: text+CHECK is chosen over native enums for additive flexibility; this is the recommended pattern. Native enums are an acceptable alternative but make adding values heavier.)

### 3.1 users

- Purpose: the account owner and security principal; owner of every user-owned row. In pure-local v0.0.1 there is exactly one user, but every table is keyed to it so multi-user is safe later (PRD §11; MANUAL_FIRST_MVP_REVISION §9).
- Privacy sensitivity: HIGH (identity). `email` is PII; never logged.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. Stable principal id. The opaque id is the only user reference safe to log. |
| email | text | yes | — | Optional in pure-local v0.0.1 (MANUAL_FIRST_MVP_REVISION §9). When present, unique. PII; never logged. |
| credential_ref | text | yes | — | Reference to an auth credential held OUTSIDE the DB (secrets manager / device secure storage). NEVER a password or token value (PRD §15). Nullable in local v0.0.1. |
| base_currency | text | no | 'ILS' | ISO-4217 code. Default per-user currency for new transactions and templates. |
| locale | text | yes | 'en' | UI locale. English-first v0.0.1; Hebrew labels are additive (CATEGORY_TAXONOMY §10). |
| settings | jsonb | yes | '{}'::jsonb | Small user preferences blob. No secrets, no PII beyond preferences. |
| created_at | timestamptz | no | now() | UTC. |
| updated_at | timestamptz | no | now() | UTC. |

- Constraints: `PRIMARY KEY (id)`; `UNIQUE (email)` (partial, where `email IS NOT NULL` — assumption: a partial unique index so multiple null emails are not blocked, though v0.0.1 has one user); `CHECK (char_length(base_currency) = 3)`.
- Indexes: PK on `id`; partial unique index on `lower(email) WHERE email IS NOT NULL`.
- Future compatibility: holds whatever auth scaffolding Phase 1 adds; `settings` absorbs future flags without schema change.

### 3.2 transactions

The atomic spend/income line. Defined in full in section 5; summarized here for completeness.

- Purpose: a single manual expense (dominant in v0.0.1) or, later, an imported cash-flow row. The single source of truth for ACTUAL spending.
- Privacy sensitivity: HIGH (core financial PII). Amounts, `raw_merchant_input`, `note`, `raw_description` never logged; never embedded.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. |
| user_id | uuid | no | — | FK → users(id) ON DELETE CASCADE. Isolation. |
| amount_minor | bigint | no | — | Signed integer agorot. `CHECK (amount_minor <> 0)`. |
| currency | text | no | 'ILS' | ISO-4217. `CHECK (char_length(currency) = 3)`. |
| transaction_type | text | no | 'expense' | One of: expense, income, refund, adjustment (section 5). |
| source | text | no | 'manual' | One of: manual, bank_import, card_import (section 5). Defaults manual. |
| merchant_id | uuid | yes | — | FK → merchants(id) ON DELETE SET NULL. Nullable (amount-only saves). Same-user (section 13). |
| category_id | uuid | yes | — | FK → categories(id) ON DELETE SET NULL. Nullable (uncategorized first-class). |
| note | text | yes | — | Free text. Sensitive; never logged. |
| occurred_on | date | no | CURRENT_DATE | Date-only financial date. Defaults today (QUICK_ADD_UX_SPEC §5). Primary date for month bucketing. |
| raw_merchant_input | text | yes | — | The verbatim typed merchant (for manual rows it doubles as the description). Sensitive; never logged (MERCHANT_NORMALIZATION_SPEC §13). |
| raw_description | text | yes | — | Verbatim source description for imported rows; null for most manual rows. Sensitive; never logged. |
| value_date | date | yes | — | Bank value date (import only). Null for manual. |
| reference | text | yes | — | Bank reference (`אסמכתא`, import only). Null for manual. |
| operation_type | text | yes | — | Bank operation code (import only). Null for manual. |
| is_card_settlement | boolean | no | false | TRUE only for imported card-settlement rows; excluded from spend (IMPORT_PIPELINE_SPEC §14). |
| account_id | uuid | yes | — | FK → accounts(id) ON DELETE SET NULL. Null for manual (import only). |
| import_batch_id | uuid | yes | — | FK → import_batches(id) ON DELETE SET NULL. Null for manual (import only). |
| dedup_hash | text | yes | — | Null for manual; deterministic hash, required+unique per user for imports (IMPORT_PIPELINE_SPEC §12). |
| created_at | timestamptz | no | now() | UTC. |
| updated_at | timestamptz | no | now() | UTC. |

- Constraints, indexes, and the full rationale (including why templates create no rows here): section 5. Index summary: section 12.

### 3.3 merchants

- Purpose: the normalized payee the user types and reuses; the anchor for recent-merchant autocomplete, merchant-to-category memory, and CategoryRules (MERCHANT_NORMALIZATION_SPEC §13).
- Privacy sensitivity: HIGH (reveals spending behavior). `normalized_merchant_name`, `display_name`, and any raw input are sensitive; never logged.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. |
| user_id | uuid | no | — | FK → users(id) ON DELETE CASCADE. Isolation. Merchants are per-user. |
| normalized_merchant_name | text | no | — | The matching/comparison key (MERCHANT_NORMALIZATION_SPEC §4). Never shown to the user. Indexed per user. |
| display_name | text | no | — | Human-facing name, user-renamable. Renaming changes display only, never the matching key or history. |
| default_category_id | uuid | yes | — | FK → categories(id) ON DELETE SET NULL. The merchant default used at the §9 precedence level 6. Nullable. |
| created_at | timestamptz | no | now() | UTC. |
| updated_at | timestamptz | no | now() | UTC. |

- Constraints: `PRIMARY KEY (id)`; `UNIQUE (user_id, normalized_merchant_name)` (one merchant per normalized key per user; this prevents duplicate rival merchants); FK `default_category_id` must be a system category (`user_id IS NULL`) or a category owned by the same user (enforced per section 13).
- Indexes: PK; `UNIQUE (user_id, normalized_merchant_name)` (doubles as the exact/normalized-lookup index); `(user_id, updated_at DESC)` for recent-merchant ordering in autocomplete.
- Future compatibility: bank/card imports propose merchant candidates that flow through the same table via the confidence ladder; imported descriptions never silently merge (MERCHANT_NORMALIZATION_SPEC §11). The original typed value is preserved via `merchant_aliases` (the first alias) rather than a separate raw column (assumption per MERCHANT_NORMALIZATION_SPEC §13: raw input "may live as the first alias").

### 3.4 merchant_aliases

- Purpose: first-class alternate raw forms that resolve to the same merchant, so variant spellings and cross-script forms collapse to one payee WITHOUT guessing (MERCHANT_NORMALIZATION_SPEC §6, §13). Generalizes the PRD `raw_aliases` array into rows so `source`/`confidence`/timestamps are storable.
- Privacy sensitivity: HIGH (alias text reveals the merchant). Never logged.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. |
| user_id | uuid | no | — | FK → users(id) ON DELETE CASCADE. Isolation. |
| merchant_id | uuid | no | — | FK → merchants(id) ON DELETE CASCADE. The merchant this alias resolves to. Same-user (section 13). |
| alias_text | text | no | — | The alternate raw form (e.g. "גולדה", "WOLT TEL AVIV"). Sensitive; never logged. |
| normalized_alias_key | text | no | — | Deterministic normalized form (MERCHANT_NORMALIZATION_SPEC §4). Indexed per user for alias_exact lookup. |
| source | text | no | 'user_confirmed' | One of: user_confirmed, import_parsed, system_suggested. Trust order high→low. Cross-script links require user_confirmed. |
| confidence | text | yes | — | The §7 match level under which it was created (exact, alias_exact, normalized_exact, recent_suggestion, contains, fuzzy_possible, none), or a trust marker for user_confirmed. |
| created_at | timestamptz | no | now() | UTC. |
| last_seen_at | timestamptz | yes | — | UTC. Updated when the alias is matched again; powers recency ranking. |

- Constraints: `PRIMARY KEY (id)`; `UNIQUE (user_id, normalized_alias_key)` (an alias key resolves to exactly one merchant per user; prevents one variant pointing at two merchants — MERCHANT_NORMALIZATION_SPEC §13); `CHECK (source IN ('user_confirmed','import_parsed','system_suggested'))`.
- Indexes: PK; `UNIQUE (user_id, normalized_alias_key)` (doubles as the alias_exact lookup index); `(merchant_id)` for "all aliases of a merchant"; `(user_id, last_seen_at DESC)` for recency-ranked autocomplete (assumption: useful for ranking, low cost).
- Future compatibility: imported descriptions create `import_parsed` aliases (medium trust) that are NOT treated as confirmed until the user uses/confirms them (MERCHANT_NORMALIZATION_SPEC §11). No ML, no fuzzy index baked in.

### 3.5 categories

- Purpose: the spending grouping shown to the user (Layer A consumer) plus the bank cash-flow categories (Layer C), seeded as stable system rows (CATEGORY_TAXONOMY §10). Full seed in section 7.
- Privacy sensitivity: LOW for system categories; MEDIUM for any future user-named category.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. |
| user_id | uuid | yes | — | FK → users(id) ON DELETE CASCADE. NULL = system/default category (shared, read-only seed). Non-null = a future user-created category. |
| key | text | yes | — | Stable English snake_case internal key for system rows (e.g. `groceries`). NULL for user-created categories (they have no canonical key). Identity, never changes once seeded (CATEGORY_TAXONOMY §10). |
| label_en | text | no | — | English display label. |
| label_he | text | yes | — | Hebrew display label placeholder (CATEGORY_TAXONOMY §10). Additive translation. |
| layer | text | no | — | One of: consumer_spending, bank_movement. (Layer B "recurring_commitment" is NOT a category row — it is a property of a template; see section 7.) |
| included_in_actual_spending | boolean | no | — | TRUE for the 14 consumer categories; FALSE for the 8 bank-movement categories. Drives the "Spent so far" sum. |
| included_in_committed_projection | boolean | no | false | FALSE for EVERY category row. Projection is a property of a template, not a category (sections 7, 9). |
| included_in_cash_flow | boolean | no | — | FALSE for consumer categories; TRUE for bank-movement categories. Drives the future cash-flow view. |
| is_system | boolean | no | false | TRUE for the 22 seeded rows; FALSE for future user categories. |
| parent_id | uuid | yes | — | FK → categories(id). Reserved for future hierarchy (MANUAL_FIRST_MVP_REVISION §9); unused in v0.0.1 (all null). |
| created_at | timestamptz | no | now() | UTC. |
| updated_at | timestamptz | no | now() | UTC. |

- Constraints: `PRIMARY KEY (id)`; `UNIQUE (key) WHERE key IS NOT NULL` (system keys unique; partial so user categories with null key are allowed — assumption: partial unique index); `CHECK (layer IN ('consumer_spending','bank_movement'))`; `CHECK (included_in_committed_projection = false)` (firm: projection is never a category flag); `CHECK (is_system = true) = (user_id IS NULL)` expressed as `CHECK ((is_system AND user_id IS NULL) OR (NOT is_system AND user_id IS NOT NULL))` (system rows have no owner; user rows do).
- Indexes: PK; partial unique on `key`; `(user_id)` for "this user's categories + system"; `(layer)` (small, optional) for layer filtering. (Assumption: the table is tiny — 22 rows + a few user rows — so most filtering is cheap regardless.)
- Future compatibility: `parent_id` reserved for hierarchy; user categories add rows with `user_id` set and `is_system=false`; the bank-movement rows already exist so v0.0.2 import needs no category seed migration (section 7 firm decision).

### 3.6 category_rules

- Purpose: turns a correction or merchant-to-category assignment into permanent learning; powers Quick Add auto-suggest (CATEGORY_TAXONOMY §9; MERCHANT_NORMALIZATION_SPEC §10). Defined in full in section 8.
- Privacy sensitivity: MEDIUM (`match_value` can be merchant PII). Never logged.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. |
| user_id | uuid | no | — | FK → users(id) ON DELETE CASCADE. Isolation. |
| match_type | text | no | — | One of: merchant_exact, merchant_contains. |
| match_value | text | no | — | The merchant's normalized name (for exact) or a fragment (for contains). |
| category_id | uuid | no | — | FK → categories(id) ON DELETE CASCADE. Target category. Same-user-or-system (section 13). |
| priority | smallint | no | 100 | Lower number = higher precedence within type; the §9 ladder governs cross-type order (section 8). |
| source | text | no | 'user_correction' | One of: system, user_correction. user_correction outranks system. |
| is_active | boolean | no | true | Inactive rules stop matching but remain for history. |
| created_at | timestamptz | no | now() | UTC. |
| updated_at | timestamptz | no | now() | UTC. |

- Constraints: `PRIMARY KEY (id)`; `CHECK (match_type IN ('merchant_exact','merchant_contains'))`; `CHECK (source IN ('system','user_correction'))`; `UNIQUE (user_id, match_type, match_value)` (a given exact/contains value maps to exactly one rule per user — "update not stack", CATEGORY_TAXONOMY §9; section 8).
- Indexes: PK; `(user_id, priority)`; `(user_id, match_type, match_value)` (the unique index, also the lookup path).
- Full conflict/precedence handling: section 8.

### 3.7 recurring_expense_templates

- Purpose: a user-created recurring commitment that PROJECTS a future charge and creates NO actual transaction in v0.0.1 (MANUAL_FIRST_MVP_REVISION §7, §9; CATEGORY_TAXONOMY §5). Defined in full in section 9.
- Privacy sensitivity: HIGH (reveals services used: gym, insurance, subscriptions). `name`, `note`, amount never logged.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | PK. |
| user_id | uuid | no | — | FK → users(id) ON DELETE CASCADE. Isolation. |
| name | text | no | — | e.g. "Gym", "Car insurance", "Netflix". Sensitive; never logged. |
| amount_minor | bigint | no | — | Signed integer agorot. `CHECK (amount_minor <> 0)`. The current projection amount. |
| currency | text | no | 'ILS' | ISO-4217. `CHECK (char_length(currency) = 3)`. |
| category_id | uuid | no | — | FK → categories(id) ON DELETE RESTRICT. A Layer A consumer key reused for grouping (CATEGORY_TAXONOMY §5). Required. |
| merchant_id | uuid | yes | — | FK → merchants(id) ON DELETE SET NULL. Optional merchant link. |
| cadence | text | no | 'monthly' | One of: weekly, monthly, yearly. |
| next_expected_date | date | no | — | Date-only. Drives "Upcoming commitments" and projection-in-month. |
| counts_in_projection | boolean | no | true | Whether this template is included in the month's projected commitment total. |
| is_active | boolean | no | true | Inactive (cancelled) templates stop projecting but stay for history. |
| note | text | yes | — | Optional. Sensitive; never logged. |
| created_at | timestamptz | no | now() | UTC. |
| updated_at | timestamptz | no | now() | UTC. |

- Constraints: `PRIMARY KEY (id)`; `CHECK (cadence IN ('weekly','monthly','yearly'))`; `CHECK (amount_minor <> 0)`; `category_id` must be system-or-same-user (section 13). `category_id` uses `ON DELETE RESTRICT` because a template must always have a category (it cannot meaningfully project into nothing — assumption; system categories are never deleted anyway).
- Indexes: PK; `(user_id, is_active, next_expected_date)` (the projection/upcoming query path, section 12).
- Firm restatement: NO trigger, job, or process turns a template into a `transactions` row in v0.0.1 (section 9).

---

## 4. Tables intentionally deferred

These are NOT created-and-used in v0.0.1's active path. Each keeps its PRD/MANUAL_FIRST shape (user_id, UTC, minor units) so introducing it later is purely additive — a new table plus, at most, activation of already-present nullable columns on `transactions`. None requires reshaping an existing v0.0.1 table.

| Table | Why deferred | When introduced |
|---|---|---|
| accounts | Manual entry has no account; the money-source abstraction is only exercised by import. Retained in schema so `transactions.account_id` has a FK target (assumption: created empty now; section 14). | v0.0.2 (bank cash-flow import). PRD §11, MANUAL_FIRST_MVP_REVISION §9. |
| import_batches | Groups an import event for traceability/rollback; nothing in manual entry creates one. Retained so `transactions.import_batch_id` has a FK target. | v0.0.2. IMPORT_PIPELINE_SPEC §15; MANUAL_FIRST_MVP_REVISION §9. |
| monthly_summaries | Precomputed per-user-month rollup; the safe aggregated bridge the AI later reads. v0.0.1 computes month totals directly from `transactions` (section 10), so a stored summary would be redundant and risks drift from actuals. | v0.1 (insights + AI). PRD §11. Must be derivable from, and reconciled against, `transactions` (review rule: summaries must never be inconsistent with transactions). |
| recurring_expenses_detected | Detected (not user-created) recurring series; needs months of history and a detection engine. v0.0.1 uses manual templates only (MANUAL_FIRST_MVP_REVISION §4). | v0.1. Distinct from `recurring_expense_templates` (manual). |
| insights | Generated user-facing observations with actions; depend on summaries/detection. | v0.1. PRD §11, §14. |
| ai_conversations | Coach chat session grouping. AI is deferred (MANUAL_FIRST_MVP_REVISION §5). | v0.1 (Phase 5). |
| ai_chat_messages | Coach chat history; references which summaries/docs were used, not raw rows. Never embedded. | v0.1. |
| financial_knowledge_documents | Curated, non-regulated coaching knowledge for RAG; system-owned, not user PII. | v0.1. |
| embeddings | pgvector index over MonthlySummary chunks + knowledge chunks, with hard `user_id`/`owner_scope` isolation. RAW TRANSACTIONS ARE NEVER EMBEDDED (firm invariant). A SEPARATE table; deletion cascades to it (section 14). pgvector may be installed in v0.0.1 but zero vectors are created. | v0.1 (Phase 5). |
| budgets | Per-category monthly target; schema ships in PRD but UI is deferred and it adds no manual-first value now. (Assumption: defer the table too in v0.0.1; it is additive when the budgeting screen earns its place.) | Late MVP / v0.1. PRD §11. |

Why deferring summaries is the right call for v0.0.1: month totals are cheap to compute live from `transactions` (section 10) on a single user's small dataset. Storing a `monthly_summaries` row now would create a second source of truth that can silently disagree with the actuals — exactly the inconsistency the review rules forbid. The summary table arrives in v0.1 as a derived, reconcilable cache, never as an authority over `transactions`.

---

## 5. Transactions table (the transaction model)

The transactions table is the single source of truth for ACTUAL spending. Its design must make amount-only saves trivial, keep "uncategorized" first-class, and carry every import field as nullable so v0.0.2/v0.0.3 add no columns.

Money and sign convention (firm):
- `amount_minor bigint` holds signed integer agorot. `currency text` defaults `'ILS'`.
- `transaction_type` carries the semantic; the sign convention (assumption, recommended and consistent with IMPORT_PIPELINE_SPEC §7): an `expense` is stored as a NEGATIVE `amount_minor` (debit/outgoing), `income` and `refund` (money back) as POSITIVE. `adjustment` may be either sign. The Home "Spent so far" sum (section 10) uses `transaction_type='expense'` and sums the absolute magnitude, so the stored sign and the displayed positive spend never conflict. (This matches the import pipeline's credit=+/debit=− convention, so manual and imported rows share one sign rule.) The `amount_minor <> 0` check forbids a zero-value transaction; QUICK_ADD_UX_SPEC §5 rejects zero at capture too.

Column-by-column rationale (full type table in section 3.2):

- `id` — `uuid` PK; stable.
- `user_id` — `uuid NOT NULL`, FK → users(id) ON DELETE CASCADE. Isolation; deletion cascade (section 14).
- `amount_minor` — `bigint NOT NULL`, `CHECK (amount_minor <> 0)`. The one truly required value to save (QUICK_ADD_UX_SPEC §5).
- `currency` — `text NOT NULL DEFAULT 'ILS'`, `CHECK (char_length(currency)=3)`.
- `transaction_type` — `text NOT NULL DEFAULT 'expense'`, `CHECK (transaction_type IN ('expense','income','refund','adjustment'))`. Quick Add defaults to `expense`; income/refund are entered only via the explicit "More" toggle (QUICK_ADD_UX_SPEC §5). `adjustment` is reserved for corrections (e.g. a manual netting entry).
- `source` — `text NOT NULL DEFAULT 'manual'`, `CHECK (source IN ('manual','bank_import','card_import'))`. Distinguishes the layers so they never blur (MANUAL_FIRST_MVP_REVISION §9). Only `manual` is produced in v0.0.1; the other values are valid-but-inactive, present so v0.0.2/v0.0.3 add no enum migration.
- `merchant_id` — `uuid NULL`, FK → merchants(id) ON DELETE SET NULL. Nullable so amount-only saves work (QUICK_ADD_UX_SPEC §3 Mode A). SET NULL on merchant delete keeps the transaction (history preserved); same-user enforced (section 13).
- `category_id` — `uuid NULL`, FK → categories(id) ON DELETE SET NULL. Nullable so "uncategorized" is first-class (CATEGORY_TAXONOMY §8). SET NULL keeps the transaction if a (future user) category is deleted; system categories are never deleted.
- `note` — `text NULL`. Optional, never required (QUICK_ADD_UX_SPEC §5). Highly sensitive (free text); never logged.
- `occurred_on` — `date NOT NULL DEFAULT CURRENT_DATE`. Date-only financial date, defaults today (QUICK_ADD_UX_SPEC §5; firm invariant: financial dates are date-only). The primary month-bucketing/ordering column. (Naming note: the prompt's `occurred_at`/`occurred_on` pair resolves to a single date-only `occurred_on`; there is no separate `occurred_at` timestamp because financial dates must be date-only — a time component would violate the invariant. Metadata time lives in `created_at`/`updated_at`.)
- `raw_merchant_input` — `text NULL`. The verbatim typed merchant, preserved for audit (MERCHANT_NORMALIZATION_SPEC §13: for a manual entry it doubles as the description). Sensitive; never logged.
- `raw_description` — `text NULL`. Verbatim source description for imported rows (IMPORT_PIPELINE_SPEC §10); null for most manual rows.
- `value_date` — `date NULL`. Bank value date (import only).
- `reference` — `text NULL`. Bank reference `אסמכתא` (import only).
- `operation_type` — `text NULL`. Bank operation code (import only).
- `is_card_settlement` — `boolean NOT NULL DEFAULT false`. TRUE only for imported card-settlement rows; those are EXCLUDED from consumer-spending totals while remaining visible as cash flow (IMPORT_PIPELINE_SPEC §14; CATEGORY_TAXONOMY §7). Always false in v0.0.1.
- `account_id` — `uuid NULL`, FK → accounts(id) ON DELETE SET NULL. Import only; null for manual.
- `import_batch_id` — `uuid NULL`, FK → import_batches(id) ON DELETE SET NULL. Import only; null for manual.
- `dedup_hash` — `text NULL`. Null for manual (no dedup needed); for imported rows it is the deterministic hash and is unique per user (IMPORT_PIPELINE_SPEC §12). Enforced by a PARTIAL unique index `UNIQUE (user_id, dedup_hash) WHERE dedup_hash IS NOT NULL` so manual rows (many nulls) are never blocked and imported rows are deduplicated (section 12).
- `created_at` / `updated_at` — `timestamptz NOT NULL DEFAULT now()`. UTC metadata.

Constraints on `transactions`:
- `PRIMARY KEY (id)`.
- `CHECK (amount_minor <> 0)`.
- `CHECK (char_length(currency) = 3)`.
- `CHECK (transaction_type IN ('expense','income','refund','adjustment'))`.
- `CHECK (source IN ('manual','bank_import','card_import'))`.
- Import-consistency check (assumption, recommended): `CHECK (source = 'manual' OR dedup_hash IS NOT NULL)` — imported rows must carry a dedup_hash; manual rows need not. This makes the dedup invariant authoritative in storage for imports without burdening manual entry.
- Partial unique: `UNIQUE (user_id, dedup_hash) WHERE dedup_hash IS NOT NULL`.
- Same-user FK enforcement for `merchant_id` and `category_id` (section 13).

Indexes: see section 12 (chiefly `(user_id, occurred_on)`, `(user_id, category_id)`, `(user_id, merchant_id)`, and the partial dedup unique).

Why recurring templates do NOT create transaction rows in v0.0.1 (firm):
- Double-counting prevention. If a template auto-inserted a transaction on its cadence, that synthetic row would collide with the real purchase when the user logs it (or when a future bank import lands the settlement), producing duplicates and corrupting "Spent so far" (MANUAL_FIRST_MVP_REVISION §7; CATEGORY_TAXONOMY §5).
- Actuals are the single source of truth. A projection is honest: it says "you have committed roughly X this month" without pretending the money moved. Keeping templates out of `transactions` keeps the actual-spend total truthful.
- Simplicity and reconciliation. v0.0.1 deliberately does NOT auto-reconcile a projection against a matching real transaction. Home shows actuals and projection SEPARATELY (sections 9, 10). Auto-matching is future work; not generating rows removes a whole class of self-inflicted duplicate bugs.

---

## 6. Merchants and aliases

Per MERCHANT_NORMALIZATION_SPEC §13. The two tables are designed together so a single `merchant_exact` rule keyed to the merchant fires across all the merchant's aliases.

merchants (section 3.3):
- `id`, `user_id`.
- `normalized_merchant_name` — the matching key (MERCHANT_NORMALIZATION_SPEC §4 deterministic pipeline). Indexed per user via the `UNIQUE (user_id, normalized_merchant_name)` constraint, which is both the dedup guard (no rival duplicate merchant) and the exact/normalized lookup path.
- `display_name` — human-facing, user-renamable; display only.
- `default_category_id` (nullable) — the merchant default at precedence level 6.
- `created_at`, `updated_at` (UTC).

merchant_aliases (section 3.4):
- `id`, `user_id`, `merchant_id`.
- `alias_text` (raw) and `normalized_alias_key` — indexed per user via `UNIQUE (user_id, normalized_alias_key)` for alias_exact lookup, and guaranteeing one alias key resolves to exactly one merchant.
- `source` — `user_confirmed | import_parsed | system_suggested`, trust high→low.
- `confidence` — the match level / trust marker.
- `created_at`, `last_seen_at` (UTC) — recency for autocomplete ranking.

Firm rules carried into the schema:
- No fuzzy auto-merge. There is no similarity index and no ML artifact in the schema (MERCHANT_NORMALIZATION_SPEC §13). Matching is deterministic exact/normalized/alias equality.
- Cross-script links require user confirmation. A Hebrew↔English link is only ever stored as a `merchant_aliases` row with `source = 'user_confirmed'` (MERCHANT_NORMALIZATION_SPEC §5, §7). The schema cannot, by itself, create a cross-script alias; only a confirmed user action does.
- The canonical exact form is the merchant's own `normalized_merchant_name` (effectively the highest-trust alias); additional `merchant_aliases` rows are the alternates around it.
- Raw typed value preserved via the first alias (assumption per §13): the input that created the merchant is retained as an alias row rather than a separate `merchants` column, so audit history is in one place.

---

## 7. Categories seed data

Per CATEGORY_TAXONOMY §10. The 14 consumer-spending categories AND the 8 bank-movement categories are seeded as system rows (`is_system = true`, `user_id = NULL`) at schema install.

FIRM DECISION (stated clearly): seed the 8 bank-movement categories NOW, even though v0.0.1 has no import. They are harmless (never offered in Quick Add — QUICK_ADD_UX_SPEC §7), stable (their keys are frozen), and seeding them now avoids a later seed migration when v0.0.2 import lands. The cost is 8 inert read-only rows; the benefit is that v0.0.2 import activates against an existing, stable category set with zero category-seed migration. This is the additive-not-rewrite principle applied to seed data.

Key-name reconciliation (canonical = the taxonomy keys): the prompt lists `bank_fee_interest` and `cash_movement`, while CATEGORY_TAXONOMY §10 uses `interest_bank_fee` and `cash_deposit_withdrawal`. The taxonomy is the source of truth (it is the finalized, approved taxonomy and the import pipeline already agrees with it). CANONICAL KEYS ARE `interest_bank_fee` and `cash_deposit_withdrawal`. The prompt's `bank_fee_interest` / `cash_movement` are noted here only as aliases-in-prose and are NOT seeded; they must not appear in the schema.

RESTATEMENT (firm): projection is a property of a recurring TEMPLATE, not of a category. Therefore `included_in_committed_projection = false` for EVERY seeded category row (enforced by a CHECK in section 3.5). Layer B (recurring commitments) has no category rows of its own — templates reuse the consumer keys below.

Full seed table (22 rows; columns: key | label_en | label_he | layer | included_in_actual_spending | included_in_committed_projection | included_in_cash_flow | is_system):

| key | label_en | label_he | layer | in_actual_spending | in_committed_projection | in_cash_flow | is_system |
|---|---|---|---|---|---|---|---|
| groceries | Groceries | קניות מזון / סופר | consumer_spending | true | false | false | true |
| eating_out | Eating out | אוכל בחוץ | consumer_spending | true | false | false | true |
| transport | Transport | תחבורה | consumer_spending | true | false | false | true |
| car_fuel | Car / fuel | רכב / דלק | consumer_spending | true | false | false | true |
| shopping | Shopping | קניות | consumer_spending | true | false | false | true |
| entertainment | Entertainment | בידור ופנאי | consumer_spending | true | false | false | true |
| subscriptions | Subscriptions | מנויים | consumer_spending | true | false | false | true |
| health | Health | בריאות | consumer_spending | true | false | false | true |
| education | Education | לימודים | consumer_spending | true | false | false | true |
| home | Home | בית | consumer_spending | true | false | false | true |
| gifts | Gifts | מתנות | consumer_spending | true | false | false | true |
| travel | Travel | נסיעות / חופשות | consumer_spending | true | false | false | true |
| personal_care | Personal care | טיפוח אישי | consumer_spending | true | false | false | true |
| other_spending | Other spending | הוצאות אחרות | consumer_spending | true | false | false | true |
| income | Income | הכנסה | bank_movement | false | false | true | true |
| incoming_transfer | Incoming transfer | העברה נכנסת | bank_movement | false | false | true | true |
| outgoing_transfer | Outgoing transfer | העברה יוצאת | bank_movement | false | false | true | true |
| credit_card_settlement | Credit card payment / settlement | חיוב כרטיס אשראי | bank_movement | false | false | true | true |
| loan_payment | Loan payment | תשלום הלוואה | bank_movement | false | false | true | true |
| interest_bank_fee | Interest / bank fee | ריבית / עמלה | bank_movement | false | false | true | true |
| cash_deposit_withdrawal | Cash deposit / withdrawal | הפקדה / משיכת מזומן | bank_movement | false | false | true | true |
| other_bank_movement | Other bank movement | תנועה בנקאית אחרת | bank_movement | false | false | true | true |

Seed notes:
- All 22 rows: `user_id = NULL`, `is_system = true`, `parent_id = NULL`, `key` set as above (the stable identity).
- Only the 14 `consumer_spending` rows appear in the Quick Add picker (QUICK_ADD_UX_SPEC §7); the 8 `bank_movement` rows are never offered in manual entry.
- `credit_card_settlement` additionally drives `transactions.is_card_settlement = true` on imported settlement rows (CATEGORY_TAXONOMY §7); the category itself carries no settlement flag — the flag lives on the transaction.
- Uncategorized is the ABSENCE of a category (`category_id IS NULL`), so it is intentionally NOT a seeded row.
- The Home spend sum (section 10) keys off `included_in_actual_spending = true` (the 14 consumer rows) plus the `transaction_type='expense'` and `is_card_settlement=false` filters, so the seed flags directly drive correct totals.

---

## 8. Category rules

Per CATEGORY_TAXONOMY §9 and MERCHANT_NORMALIZATION_SPEC §10. The `category_rules` table (section 3.6) turns corrections into learning.

Fields: `match_type` (merchant_exact | merchant_contains), `match_value`, `category_id`, `priority`, `source` (system | user_correction), `is_active`, `created_at`, `updated_at`.

Precedence ladder (the authoritative §9 order, highest first), used by the application to resolve a category suggestion:
1. user_correction `merchant_exact`
2. user_correction `merchant_contains`
3. system `merchant_exact`
4. system `merchant_contains`
5. recent-merchant memory (the category last used for the merchant — derived from transaction history, not a rule row)
6. merchant default (`merchants.default_category_id`)
7. uncategorized (`category_id = NULL`)

How the schema supports the ladder:
- `source` (user_correction vs system) and `match_type` (exact vs contains) together place a rule on levels 1–4. The application resolves in this fixed order; the first match wins.
- `priority smallint` breaks ties WITHIN a level (lower = stronger). Ties at the same priority are broken by most-recently-updated (`updated_at DESC`) — the newer correction reflects current intent (CATEGORY_TAXONOMY §9).
- Levels 5–7 are not rule rows: recent-merchant memory is computed from `transactions` (most-recent `category_id` for that `merchant_id`), merchant default is `merchants.default_category_id`, and uncategorized is the null fallback.

Conflict handling (firm):
- User corrections win over system rules. `source='user_correction'` always outranks `source='system'` by the ladder, independent of `priority`.
- One merchant maps to one category at a time — UPDATE, not stack. The `UNIQUE (user_id, match_type, match_value)` constraint enforces that a given `merchant_exact` value (the merchant's normalized name) or a given `contains` fragment has exactly ONE rule row per user. A new user correction for the same merchant UPDATES the existing row (changing `category_id`, refreshing `updated_at`) rather than inserting a rival (CATEGORY_TAXONOMY §9; MERCHANT_NORMALIZATION_SPEC §10). The application performs an upsert keyed on `(user_id, match_type, match_value)`.
- Alias coverage. A `merchant_exact` rule is keyed to the merchant's `normalized_merchant_name`; because all of a merchant's aliases resolve to that merchant, one rule fires across every alias (MERCHANT_NORMALIZATION_SPEC §10). No per-alias rule is needed.
- Going-forward by default. Rules apply to future categorization; bulk re-categorization of existing transactions is an explicit, optional, user-initiated action — never automatic (CATEGORY_TAXONOMY §9). The schema does not auto-rewrite history.
- When NOT to create a rule (enforced by the application, not the schema): one-off `other_spending` entries, silent edits without the explicit "Always categorize…?" confirmation, very short/generic `contains` fragments, and blank-merchant transactions (MERCHANT_NORMALIZATION_SPEC §10).

---

## 9. Recurring expense templates

Per MANUAL_FIRST_MVP_REVISION §7, §9 and CATEGORY_TAXONOMY §5. The `recurring_expense_templates` table (section 3.7) captures predictable commitments without a detection engine and without generating transactions.

Fields: `id`, `user_id`, `name`, `amount_minor`, `currency`, `category_id` (required; a Layer A consumer key reused for grouping), `merchant_id` (nullable), `cadence` (weekly | monthly | yearly), `next_expected_date`, `counts_in_projection` (default true), `is_active` (default true), `note` (nullable), `created_at`, `updated_at`.

Semantics:
- Contributes to PROJECTED commitments ONLY. A template's `amount_minor` is a projection, never spend. It is summed into "Upcoming commitments" on Home (section 10) when `is_active = true` AND `counts_in_projection = true` AND `next_expected_date` falls in the viewed month.
- Creates NO transaction automatically (firm). No trigger, scheduled job, or process inserts a `transactions` row from a template in v0.0.1. The actuals (manual transactions) remain the single source of truth (section 5).
- `counts_in_projection` lets the user exclude a commitment from projection (e.g. an annual fee accounted for separately) without deleting the template.
- `is_active = false` (cancelled subscription) stops projection but keeps the row for history.
- Category reuse, not duplication. A gym template uses `health`; a streaming template uses `subscriptions` (CATEGORY_TAXONOMY §5). The category KEY is shared with consumer spending; the LAYER (commitment vs spend) differs. There are no Layer B category rows — projection is the template's property, which is exactly why every category row has `included_in_committed_projection = false` (section 7).
- Cadence drives the next-expected-date math in the application; the schema stores the cadence and the next date but does not itself advance dates (assumption: the application updates `next_expected_date` when appropriate; v0.0.1 may simply display the stored next date).

---

## 10. Home dashboard query support

How the schema supports each Home element (QUICK_ADD_UX_SPEC §12; CATEGORY_TAXONOMY §12; MANUAL_FIRST_MVP_REVISION §10). All queries filter by `user_id` first (isolation, section 13). "This month" means `occurred_on` within `[month_start, month_end]`.

1. Spent so far this month (the headline, Layer A actual):
   - Tables/fields: `transactions` joined to `categories`.
   - Query shape: sum the magnitude of `amount_minor` over `transactions` where `user_id = :u` AND `source = 'manual'` AND `transaction_type = 'expense'` AND `is_card_settlement = false` AND `occurred_on` in the month AND (`category_id IS NULL` OR the category's `included_in_actual_spending = true`). Including `category_id IS NULL` is deliberate: uncategorized expenses are real spend and DO count (QUICK_ADD_UX_SPEC §3 Mode A). The `is_card_settlement = false` and `source = 'manual'` filters keep future imported settlements/cash-flow out of spend by construction.
   - Index: `(user_id, occurred_on)`.

2. Top actual spending category:
   - Tables/fields: `transactions` grouped by `category_id`, joined to `categories` to restrict to `included_in_actual_spending = true`.
   - Query shape: the same spend filter as (1) but `category_id IS NOT NULL`, grouped by `category_id`, ordered by summed magnitude DESC, limit 1. Uncategorized is excluded from the ranking (it is not a category — CATEGORY_TAXONOMY §8).
   - Index: `(user_id, category_id)` plus the month filter.

3. Recent transactions:
   - Tables/fields: `transactions` (with `merchant_id` → `merchants.display_name`, `category_id` → label).
   - Query shape: `WHERE user_id = :u` ORDER BY `occurred_on DESC, created_at DESC` LIMIT N. Includes uncategorized rows, clearly marked (QUICK_ADD_UX_SPEC §12).
   - Index: `(user_id, occurred_on)`.

4. Uncategorized count (the "needs a category" review):
   - Tables/fields: `transactions`.
   - Query shape: `COUNT(*) WHERE user_id = :u AND category_id IS NULL AND occurred_on` in month (or all-time, per the review surface). `category_id IS NULL` is the first-class uncategorized state.
   - Index: `(user_id, occurred_on)`; a partial index `(user_id) WHERE category_id IS NULL` is optional if the count is hot (section 12).

5. Upcoming recurring commitments (Layer B projection):
   - Tables/fields: `recurring_expense_templates`.
   - Query shape: sum `amount_minor` (and/or list) `WHERE user_id = :u AND is_active = true AND counts_in_projection = true AND next_expected_date` in the viewed month. This is the "Upcoming commitments" number and the forward-looking list.
   - Index: `(user_id, is_active, next_expected_date)`.

6. Known this month = actual + projected, clearly separated:
   - The application presents (1) and (5) as two labelled numbers ("Spent X · Committed Y") and never sums them into one ambiguous figure (CATEGORY_TAXONOMY §12; firm UX rule). The schema keeps them separable BY CONSTRUCTION: actuals come from `transactions`, projections from `recurring_expense_templates`; there is no row that is both, so they cannot accidentally merge.

Note on future cash-flow (Layer C): when bank import lands (v0.0.2), the cash-flow view sums imported rows (`source IN ('bank_import')`) separately, with `is_card_settlement = true` rows shown but excluded from spend. The Home spend query in (1) already excludes them, so adding import does not corrupt "Spent so far."

---

## 11. Privacy and logging implications

Per PRD §15, MERCHANT_NORMALIZATION_SPEC §14, QUICK_ADD_UX_SPEC §15, IMPORT_PIPELINE_SPEC §17. Merchant data and notes reveal spending behavior (habits, health, beliefs, relationships) and are PII.

Sensitive fields that MUST NEVER be logged:
- `transactions.raw_merchant_input`, `transactions.raw_description`, `transactions.note`.
- `transactions.amount_minor` (in any unit), and any combination that re-identifies a purchase.
- `merchants.normalized_merchant_name`, `merchants.display_name`.
- `merchant_aliases.alias_text`, `merchant_aliases.normalized_alias_key`.
- `category_rules.match_value` (can be merchant text).
- `recurring_expense_templates.name`, `.note`, `.amount_minor`.
- `users.email`, `users.credential_ref`.
- The category text WHEN paired with an amount or merchant (a category correction tied to an amount is re-identifying).

Safe to log (structured: IDs / counts / enums only):
- Opaque IDs: `user_id`, `transaction_id`, `merchant_id`, `alias_id`, `category_id`, `rule_id`, `template_id`. (`user_id` is an opaque uuid, never the email.)
- Counts: number of merchants matched, suggestions shown, rows in a result, uncategorized count.
- Enum level names: `merchant_confidence` level (exact | alias_exact | normalized_exact | recent_suggestion | contains | fuzzy_possible | none), `match_type`, rule `source`, `transaction_type`, `source`, `cadence` — the name only, never the text that produced it.
- Event types and success/failure status; duration buckets (e.g. <2s, 2–5s, >5s) to verify the five-second goal (QUICK_ADD_UX_SPEC §15).

Storage and embedding rules:
- All sensitive fields are stored in SQL (the owner sees them in-app) and are NEVER embedded. Raw transactions live in SQL only (firm invariant). pgvector may be installed in v0.0.1 but zero vectors are created (MANUAL_FIRST_MVP_REVISION §5).
- `credential_ref` is a reference to a credential held in a secrets manager / device secure storage — never a password, token, or key value in a DB row (PRD §15).
- Debugging a wrong match is done by IDs and confidence-level enums, never by logging the typed text (MERCHANT_NORMALIZATION_SPEC §14).

Secrets discipline (challenge per review rules): this schema stores NO secrets, tokens, or keys. `users.credential_ref` is explicitly a reference, not a secret. Any design that proposed storing an auth token, API key, or encryption key in a column would be rejected here.

---

## 12. Index strategy

Indexes target the manual-first hot paths: per-user/per-month transaction queries, merchant/alias lookups for Quick Add, rule resolution, and the projection query. All composite indexes lead with `user_id` because every query is user-scoped (isolation).

transactions:
- `(user_id, occurred_on)` — month and date-range queries; Home "Spent so far", recent transactions, category drill-downs. The primary workhorse.
- `(user_id, category_id)` — category rankings and category-detail lists. (Assumption: optionally `(user_id, category_id, occurred_on)` if month-scoped category queries dominate; start with `(user_id, category_id)` and add the month column only if profiling shows need.)
- `(user_id, merchant_id)` — per-merchant history (recent-merchant memory, merchant detail).
- PARTIAL UNIQUE `(user_id, dedup_hash) WHERE dedup_hash IS NOT NULL` — import dedup authority (IMPORT_PIPELINE_SPEC §12). Partial so the many manual rows with null `dedup_hash` are never blocked; active only when imports arrive.
- Optional PARTIAL `(user_id) WHERE category_id IS NULL` — fast uncategorized count if that review surface is hot (assumption; add on need).

merchants:
- UNIQUE `(user_id, normalized_merchant_name)` — exact/normalized merchant lookup AND the no-duplicate-merchant guard.
- `(user_id, updated_at DESC)` — recent-merchant ordering for autocomplete chips (QUICK_ADD_UX_SPEC §6).

merchant_aliases:
- UNIQUE `(user_id, normalized_alias_key)` — alias_exact lookup AND the one-alias-key-one-merchant guard.
- `(merchant_id)` — "all aliases of a merchant" (rule firing across aliases).
- `(user_id, last_seen_at DESC)` — recency-ranked autocomplete (assumption; low cost).

category_rules:
- `(user_id, priority)` — rule resolution ordered by precedence.
- UNIQUE `(user_id, match_type, match_value)` — the update-not-stack guard and the lookup path for a specific merchant/fragment.

categories:
- PARTIAL UNIQUE `(key) WHERE key IS NOT NULL` — system key uniqueness.
- `(user_id)` — a user's categories plus system (the table is tiny; this is cheap insurance).

recurring_expense_templates:
- `(user_id, is_active, next_expected_date)` — the projection / "Upcoming commitments" query path (section 10 item 5).

users:
- PARTIAL UNIQUE on `lower(email) WHERE email IS NOT NULL` — login lookup, multi-null-safe.

Note on partial/unique indexes: the dedup unique, the system-key unique, the email unique, the merchant unique, and the alias-key unique are all integrity-bearing (they prevent duplicates), not merely performance aids. The two `WHERE … IS NOT NULL` partials (dedup, email) exist specifically so nullable columns do not block legitimate rows.

---

## 13. Constraints and data integrity

Money and required-field constraints:
- `transactions.amount_minor <> 0` (a zero expense is not a movement; QUICK_ADD_UX_SPEC §5) and `recurring_expense_templates.amount_minor <> 0`.
- `currency` required and `char_length(currency) = 3` on `transactions`, `recurring_expense_templates`, and `users.base_currency`. ILS default everywhere.

Enum/check constraints:
- `transactions.transaction_type IN ('expense','income','refund','adjustment')`.
- `transactions.source IN ('manual','bank_import','card_import')`.
- `category_rules.match_type IN ('merchant_exact','merchant_contains')`; `category_rules.source IN ('system','user_correction')`.
- `merchant_aliases.source IN ('user_confirmed','import_parsed','system_suggested')`.
- `recurring_expense_templates.cadence IN ('weekly','monthly','yearly')`.
- `categories.layer IN ('consumer_spending','bank_movement')`; `categories.included_in_committed_projection = false` (projection is never a category flag); the system/owner consistency check `((is_system AND user_id IS NULL) OR (NOT is_system AND user_id IS NOT NULL))`.

Ownership and isolation:
- `user_id` on every user-owned table (`transactions`, `merchants`, `merchant_aliases`, `category_rules`, `recurring_expense_templates`; and user-created `categories`). System categories are the ONLY rows with `user_id IS NULL`.
- A category referenced by a transaction, rule, merchant default, or template must be EITHER a system category (`user_id IS NULL`) OR owned by the SAME user. A merchant referenced by a transaction, alias, or template must be owned by the SAME user. Postgres FKs alone cannot express "same user_id," so this is enforced by (assumption, recommended) one of:
  - (a) Application-layer checks on write that the referenced row's `user_id` matches (or is null for system categories), PLUS
  - (b) Composite FKs to make same-user structural where it matters: declare `UNIQUE (id, user_id)` on `merchants` and on `transactions`, then have referencing tables carry `user_id` and use a composite FK `(merchant_id, user_id) → merchants(id, user_id)`. For categories, because system rows have `user_id IS NULL`, a pure composite FK does not cover the system case, so the category same-user-or-system rule is enforced in the application (and optionally a trigger). Recommendation: use composite FKs for merchant references (clean, structural) and application-layer enforcement for the category-or-system rule, with a CHECK that the referencing row's `user_id` is set.
- Cross-user reads are prevented by always filtering on `user_id` in every query (section 12 indexes lead with `user_id`); no query path omits it.

Uniqueness/dedup:
- `merchant_aliases`: `UNIQUE (user_id, normalized_alias_key)` (one alias key → one merchant per user).
- `merchants`: `UNIQUE (user_id, normalized_merchant_name)` (no duplicate rival merchant).
- `category_rules`: `UNIQUE (user_id, match_type, match_value)` (update-not-stack).
- `categories`: `UNIQUE (key) WHERE key IS NOT NULL` (system keys unique).
- `transactions`: `UNIQUE (user_id, dedup_hash) WHERE dedup_hash IS NOT NULL` (import dedup) and `CHECK (source = 'manual' OR dedup_hash IS NOT NULL)` (imports must carry a dedup hash).
- `users`: `UNIQUE (lower(email)) WHERE email IS NOT NULL`.

Deletion behavior (export/delete must be easy — review rule):
- `ON DELETE CASCADE` from `users` to all user-owned tables (a full account delete removes everything; section 14).
- `transactions.merchant_id` / `transactions.category_id`: `ON DELETE SET NULL` (deleting a merchant or future user-category preserves the transaction as history, downgrading it to merchant-less/uncategorized).
- `merchant_aliases.merchant_id`: `ON DELETE CASCADE` (aliases have no meaning without their merchant).
- `recurring_expense_templates.category_id`: `ON DELETE RESTRICT` (a template must keep a category; system categories are never deleted, so this never blocks in practice).

---

## 14. Migration plan later (additive, never a rewrite)

The central guarantee: because `transactions` already carries every import field as nullable (`account_id`, `import_batch_id`, `raw_description`, `value_date`, `reference`, `operation_type`, `is_card_settlement`, `dedup_hash`), no future milestone reshapes the transactions table. Future work is new tables plus activation of present columns.

- v0.0.2 — bank cash-flow import:
  - Activate `accounts` and `import_batches` (create them if deferred at install; assumption: created empty at install so FK targets already exist — section 4).
  - Populate the already-present `transactions.account_id`, `import_batch_id`, `raw_description`, `value_date`, `reference`, `operation_type`, `dedup_hash`, and set `source = 'bank_import'`. The partial unique `(user_id, dedup_hash)` and the `CHECK (source='manual' OR dedup_hash IS NOT NULL)` become active for these rows.
  - Card-settlement rows set `is_card_settlement = true` and use the seeded `credit_card_settlement` category — already excluded from spend by the Home query (section 10). No category seed migration (bank categories were seeded in v0.0.1, section 7).
  - No ALTER to existing manual rows; no transactions-table rewrite.

- v0.0.3 — itemized card import:
  - Add a card import profile/`accounts.type = 'card'`; set `source = 'card_import'` (already a valid enum value). Itemized purchases become Layer A spend through the same merchant/category/rule machinery (CATEGORY_TAXONOMY §13). The bank-level settlement remains excluded, so no double count by construction.

- v0.1 — MonthlySummary, recurring detection, insights, AI/RAG:
  - Add `monthly_summaries` as a DERIVED cache reconcilable against `transactions` (it must never become an authority that drifts from actuals — review rule). Add `recurring_expenses_detected`, `insights`, `ai_conversations`, `ai_chat_messages`, `financial_knowledge_documents`.
  - Add `embeddings` as a SEPARATE pgvector table indexing MonthlySummary chunks + knowledge chunks ONLY, with a hard `user_id`/`owner_scope` isolation filter on every query. Raw transactions are NEVER embedded (firm invariant). pgvector, installed in v0.0.1, gets its first vectors here.

- Export / delete (PRD §15, §17): export reads all user-owned rows by `user_id` into a portable format. Delete is a single `DELETE FROM users WHERE id = :u` that CASCADES to `transactions`, `merchants`, `merchant_aliases`, `category_rules`, `recurring_expense_templates`, and (when they exist) `accounts`, `import_batches`, `monthly_summaries`, `insights`, `ai_conversations`, `ai_chat_messages`, and the user-scoped `embeddings` rows. The cascade is designed in from v0.0.1 so deletion is never hard later (review rule: never make deletion/export difficult). System categories and system knowledge documents are not user-owned and are not deleted.

Emphasis: the deferred fields already present on `transactions` mean v0.0.2 and v0.0.3 add zero columns to that table. That is the whole point of carrying them nullable now.

---

## 15. Test cases (schema-level)

Each: setup → expected. These define schema acceptance; no code.

1. Amount-only transaction:
   - Setup: insert into `transactions` with `user_id`, `amount_minor = -3300`, `transaction_type='expense'`, `source='manual'`, `occurred_on` defaulted, `merchant_id = NULL`, `category_id = NULL`.
   - Expected: insert succeeds; row counts toward "Spent so far" (section 10 query 1, because uncategorized expenses count) and appears in the uncategorized count (query 4). No rule, no merchant required.

2. Transaction with merchant and category:
   - Setup: a merchant "Golda" and category `eating_out` exist for the user; insert a transaction referencing both.
   - Expected: insert succeeds; row counts in "Spent so far" and in the `eating_out` total; contributes to Top category.

3. Merchant alias creation (user-confirmed):
   - Setup: merchant "Golda" exists; insert a `merchant_aliases` row with `alias_text='גולדה'`, `normalized_alias_key` set, `source='user_confirmed'`, `merchant_id` = Golda.
   - Expected: insert succeeds; the alias key is unique per user; a later lookup of `גולדה` resolves to Golda (alias_exact), and Golda's `merchant_exact` rule fires for it.

4. Cross-script alias pending confirmation:
   - Setup: user types `גולדה`; no `user_confirmed` alias exists.
   - Expected: the schema stores NO cross-script alias automatically. Only an explicit insert with `source='user_confirmed'` (test 3) links them. Until then, a separate merchant may exist; the schema never auto-merges (MERCHANT_NORMALIZATION_SPEC §5). (Verifies that a `system_suggested`/`import_parsed` alias does not cause a silent merge.)

5. Category rule priority / update-not-stack:
   - Setup: insert a system `merchant_contains` rule "wolt"→`eating_out`. Then upsert a user `merchant_exact` rule for normalized "wolt"→`shopping`. Then upsert again "wolt"→`subscriptions`.
   - Expected: the `UNIQUE (user_id, match_type, match_value)` constraint means the user `merchant_exact` rule is UPDATED (one row, `category_id=subscriptions`), not stacked. Resolution returns `subscriptions` (user_correction merchant_exact outranks system contains).

6. Recurring template does NOT create a transaction:
   - Setup: insert a `recurring_expense_templates` row (Gym, `health`, monthly, `next_expected_date` this month, `counts_in_projection=true`, `is_active=true`).
   - Expected: `SELECT COUNT(*) FROM transactions WHERE user_id=:u` is unchanged. The template contributes only to the projection query (section 10 query 5). No transaction row exists for the template.

7. Home query returns actuals and commitments separately:
   - Setup: one manual expense (₪33 `eating_out`) and one active template (₪120 `health`, projects this month).
   - Expected: query 1 returns ₪33 actual; query 5 returns ₪120 committed; there is no query that returns ₪153 as a single spend figure. The two come from different tables and are never summed in the schema.

8. user_id isolation (no cross-user reads):
   - Setup: two users, each with transactions.
   - Expected: every section-10 query filtered by `user_id = :u` returns only that user's rows. No query path omits `user_id`. (Verifies isolation by construction.)

9. No invalid foreign ownership:
   - Setup: user A inserts a transaction referencing user B's merchant (or user B's user-created category).
   - Expected: REJECTED — by the composite same-user FK on merchant references and by the application/trigger same-user-or-system check on category references (section 13). A system category (`user_id IS NULL`) is accepted for any user.

10. Seed categories exist:
    - Setup: fresh schema install.
    - Expected: exactly 22 system categories exist (`is_system=true`, `user_id IS NULL`): 14 `consumer_spending` (`included_in_actual_spending=true`) and 8 `bank_movement` (`included_in_cash_flow=true`); every row has `included_in_committed_projection=false`; keys match section 7 exactly, including canonical `interest_bank_fee` and `cash_deposit_withdrawal`.

11. Dedup integrity (future-import guard, verifiable now):
    - Setup: insert two transactions for the same user with the same non-null `dedup_hash`.
    - Expected: the second is REJECTED by `UNIQUE (user_id, dedup_hash) WHERE dedup_hash IS NOT NULL`. Two manual rows with `dedup_hash = NULL` are both ACCEPTED (the partial index does not block nulls).

12. Privacy/logging (assertion, schema-adjacent):
    - Setup: any write path with logging enabled.
    - Expected: logs contain only IDs/counts/enum names; no `raw_merchant_input`, `note`, `amount_minor`, merchant/alias text, `match_value`, or `email` appears in any log line (section 11).

---

## 16. Acceptance criteria

This schema is complete when ALL hold:
1. It supports the Quick Add UX without workarounds: amount-only saves, optional merchant/category, default-today `occurred_on`, save-first rule promotion (nullable `merchant_id`/`category_id`, `CURRENT_DATE` default, upsert-keyed `category_rules`).
2. Amount-only transactions are first-class: a non-zero `amount_minor` with null merchant and null category persists and counts toward "Spent so far."
3. Merchant aliasing is safe: first-class `merchant_aliases` rows with `source`/`confidence`/timestamps; cross-script links only via `user_confirmed`; no fuzzy/ML index; `UNIQUE (user_id, normalized_alias_key)`.
4. Category rules learn correctly: `merchant_exact`/`merchant_contains`, `priority`, `source`, the §9 precedence ladder, and update-not-stack via `UNIQUE (user_id, match_type, match_value)`.
5. Recurring commitments project without spending: `recurring_expense_templates` with `counts_in_projection`/`is_active`/`cadence`/`next_expected_date`, and NO transaction rows generated.
6. Actual spending and commitments stay separate by construction: actuals from `transactions`, projections from templates; no row is both; Home never needs to disentangle them.
7. The model is ready for an API contract: every entity, field, type, default, constraint, and index is fixed; enum values and the sign convention are stated.
8. AI/RAG/import overbuild is avoided: no embeddings table, no summaries, no accounts/import_batches actively used; pgvector unused; only the seven active tables.
9. Future import/AI tables add without a rewrite: `transactions` carries all import fields nullable now; deferred tables keep PRD shape; deletion cascade is designed in (sections 4, 14).
10. Firm invariants honored: PostgreSQL; signed integer minor units + ILS default; UTC `timestamptz` metadata; date-only `occurred_on`/`value_date`/`next_expected_date`; `user_id` everywhere; raw transactions in SQL only and never embedded; no PII in logs.

---

## 17. Next recommended prompt

Send this after approving this schema (the schema entities are now frozen; the API contract is written against them):

> "Acting as the backend-api-engineer agent with the product-architect agent, and using docs/PRD_V0_1.md as the long-term vision, docs/MANUAL_FIRST_MVP_REVISION.md as the governing v0.0.1 decision, docs/CATEGORY_TAXONOMY.md as the finalized taxonomy, docs/MERCHANT_NORMALIZATION_SPEC.md as the merchant-matching logic, docs/QUICK_ADD_UX_SPEC.md as the settled interaction model, and docs/DATABASE_SCHEMA_V0_0_1.md as the FROZEN data model, produce docs/API_CONTRACT_V0_0_1.md for manual-first v0.0.1. Define the REST/JSON endpoints needed by Quick Add and Home against the frozen entities (users, transactions, merchants, merchant_aliases, categories, category_rules, recurring_expense_templates): create/list/edit a transaction (amount-only and fully categorized), merchant autocomplete and resolution through the confidence ladder, category suggestion via the precedence ladder, the 'Always categorize…?' rule upsert, the cross-script 'Same as Golda?' alias confirmation, recurring template CRUD (projection-only), and the Home rollups ('Spent so far', 'Upcoming commitments', top category, recent transactions, uncategorized count) with actuals and projection ALWAYS returned as separate fields. For each endpoint define method, path, request/response shapes (money as signed integer minor units, ILS default; dates date-only; timestamps UTC), validation, error codes, and the privacy rule that no request/response is ever logged with raw merchant text, notes, or amounts — only IDs/counts/enums. Honor every firm invariant and do not introduce any deferred table (accounts, import_batches, summaries, embeddings) into the active contract. Planning and specification only, no code, no migrations."

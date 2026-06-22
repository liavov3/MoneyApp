# Money App — Manual-First MVP Revision (v0.0.1 pivot)

Status: Product revision. Planning only. No code, no screens, no implementation.
Owner: Product Architect (lead), synthesizing mobile-ux-designer, database-engineer, backend-api-engineer, fintech-researcher, and security-privacy-engineer perspectives.
Decision authority: Founder product decision (2026-06-14).
Inputs (approved, all read):
- docs/PRD_V0_1.md — long-term vision. KEPT, not discarded.
- docs/MVP_EXECUTION_ALIGNMENT.md — the build filter. This revision REVISES its v0.0.1 definition.
- docs/IMPORT_PIPELINE_SPEC.md — import spec. STAYS VALID, repositioned as a later cash-flow source.
- docs/IMPORT_SPEC_BANK_STATEMENT_HEBREW_V1.md + docs/SANITIZED_BANK_STATEMENT_SAMPLE.csv — the Israeli bank profile. STAYS VALID, repositioned.
Date: 2026-06-14

Firm prior decisions carried forward UNCHANGED: signed integer minor units; UTC timestamps for metadata; user_id on every user-owned row; raw transactions in SQL only, never embedded; privacy-first logging (never log raw descriptions, amounts, PII, or filenames); FastAPI single backend; Postgres + pgvector; the card-settlement exclusion flag concept from IMPORT_PIPELINE_SPEC section 14 to prevent double-counting bank settlements against manual spending.

---

## 1. Why the pivot is needed

The previous build filter (MVP_EXECUTION_ALIGNMENT.md) made v0.0.1 import-first: prove the loop by importing a CSV/Excel file, categorizing it, and showing a monthly overview. That order was correct for de-risking parsing, but it was wrong about what makes the app usable for the founder day to day. The founder is also the sole v0.0.1 user, so "usable for the founder" is the only acceptance bar that matters right now.

Three hard realities make import-first too painful for personal daily use:

1. Multiple credit cards. The founder's real spending is spread across several credit cards. No single export captures it. The bank current-account statement (the one shape we actually have a sample for, `bank_statement_hebrew_v1`) only shows the monthly card SETTLEMENT — one aggregate line per card per month, not the individual purchases. The itemized purchases live in separate per-card exports. So import-first does not even deliver the core promise (where did my money go), it delivers cash-flow movements.

2. iPhone limitations, no reliable automatic capture. The founder uses an iPhone. There is no reliable, supported iOS MVP path to automatically capture Apple Pay / Wallet transaction notifications. FinanceKit, Wallet, and open banking are out of scope (PRD section 6) and not realistically buildable by a solo developer as a first milestone. So the "automatic" escape hatch that would make import-first painless does not exist for us.

3. Manual CSV export friction. The only honest import-first workflow is: every month, log into each bank and each credit-card website, export a file per source, sanitize, and import several files. For occasional analysis that is fine. For a tool meant to be used DAILY to understand and improve spending, exporting and importing multiple files every month is too much friction. A tool you have to feed once a month with chores is a tool you stop using, and an unused finance app produces zero insight.

Conclusion: import-first optimizes for the hardest engineering risk (parsing) but starves the product of the one thing it needs to earn trust — being opened and used. We pivot v0.0.1 to manual-first. The fastest path to real, daily, consumer-level spending data is the user typing a purchase in under five seconds, right after they make it. Bank import does not disappear; it is repositioned (section 8).

---

## 2. New v0.0.1 goal

v0.0.1 is a fast manual spending tracker with manual recurring expenses and a simple monthly category overview.

In one sentence: the founder can, in under five seconds, log a purchase the moment it happens, and at any time open Home to see how much they have spent this month, by category, plus what recurring commitments are still coming.

This goal is deliberately smaller than the prior v0.0.1 and far smaller than PRD v0.1. It proves a different but more important loop than import-first did: capture real spending with near-zero friction, then reflect it back simply. If that loop is habit-forming and trustworthy, every later layer (bank cash-flow import, card-import assistant, insights, AI coach) has clean, real, user-entered data to stand on. If it is not, nothing else matters.

The PRD remains the long-term vision unchanged. This is the smallest first build that serves the PRD's core promise (understand your situation in five seconds; every insight leads to an action) on data we can actually get today.

---

## 3. What stays from the original plan

Nothing strategic is thrown away. The pivot reorders, it does not rewrite. The following are KEPT exactly:

- Categories. A small, sane default taxonomy remains central — and is now MORE useful immediately (section 4).
- Merchants / counterparties. The normalized payee concept stays; for manual entry it becomes the "merchant" the user types and reuses.
- Category rules. A correction or a merchant-to-category assignment still creates/updates a rule so the system learns. This is the difference between a labeller and a coach.
- Signed integer minor units. Money is always a signed integer in minor units plus a currency code. Unchanged.
- user_id on every user-owned row. Multi-user-safe by construction even with one user. Unchanged.
- UTC timestamps for metadata (created_at, updated_at, imported_at). Calendar dates (purchase date) stay date-only. Unchanged.
- Privacy-first logging. Never log raw descriptions, amounts, PII, or filenames. IDs, counts, and event types only. Unchanged.
- Future import architecture. The Account and ImportBatch abstractions are RETAINED in the schema (optional/deferred for active use) so bank cash-flow import and later card import slot in without a rewrite. Unchanged intent from MVP_EXECUTION_ALIGNMENT.md issue 15.
- Bank-statement import as later cash-flow support. IMPORT_PIPELINE_SPEC.md and the Hebrew bank profile stay valid and are not deleted; they become the v0.0.2 cash-flow source (section 8).
- The card-settlement exclusion flag (IMPORT_PIPELINE_SPEC section 14). Retained as a first-class concept so bank settlements never double-count against manual spending once import arrives.
- The stack. FastAPI single backend, Postgres + pgvector (extension installed, no vectors created in v0.0.1), REST/JSON, local/dev only. Unchanged.
- AI/RAG architecture intent. Still architected for, still deferred. Raw transactions never embedded.

---

## 4. What changes

- Manual expense entry becomes the CORE v0.0.1 flow. It moves from a secondary "for cases a file does not cover" feature (MVP_EXECUTION_ALIGNMENT.md section 5, item 6) to the primary capture path the whole product is built around.
- Bank import moves OUT of the v0.0.1 critical path. It becomes v0.0.2 (primary) or an OPTIONAL secondary flow in v0.0.1 if it is trivially cheap to include. It is no longer a gate on shipping v0.0.1.
- AI / RAG remains DEFERRED, as before. No change to that deferral; the data foundation argument still holds.
- Recurring expenses become MANUAL setup first. The prior plan deferred recurring DETECTION (which needs months of history). We do not wait for detection. Instead, v0.0.1 lets the user MANUALLY create recurring expense templates (gym, insurance, phone, subscriptions). Automatic detection from history stays deferred to a later version.
- Consumer-spending categories become useful IMMEDIATELY. This is the key unlock. A bank statement only shows card settlements, so consumer categories (Groceries, Eating out, Transport, Shopping) cannot be populated from it without the itemized card files. But when the user MANUALLY enters an actual purchase, they enter the real category at the moment of spending. Manual-first makes the consumer taxonomy live on day one, which import-first could not.

What does NOT change: the import spec's correctness rules, the bank profile, the money/privacy invariants, and the long-term PRD vision.

---

## 5. v0.0.1 scope

INCLUDE (the manual-first core):

- Quick Add Expense: amount, merchant/counterparty, category, date (defaults to today), optional note.
- Recent merchants: surface recently used payees for one-tap reuse.
- Merchant-to-category memory: remember the category last used for a merchant and auto-suggest it next time (a CategoryRule under the hood).
- Manual recurring expenses: user-created templates with a cadence and expected next charge (section 7).
- Monthly total from manually entered transactions (the actuals).
- Category totals: spend per category for the month, ranked.
- Simple Home dashboard: this month's manual spending, recurring commitments, top category, recent transactions (section 10).
- Transaction list: chronological list of entered transactions for the month.
- Edit transaction / edit category: correct any field; a category change can create/update a rule.

EXPLICITLY EXCLUDE from v0.0.1:

- AI coach chat.
- RAG / embeddings (pgvector installed, zero vectors created).
- Automatic bank connection / open banking / live APIs.
- Apple Pay / Apple Wallet / FinanceKit notification capture.
- Credit-card itemized CSV import (the multi-file, per-card shape) — future work.
- Recurring DETECTION from history (only manual templates in v0.0.1).
- Unusual-spending detection.
- Complex insights, charts, configurable dashboards, budgets UI.
- Bank cash-flow CSV import is NOT required for v0.0.1; it is v0.0.2, optional-secondary at most (section 8).

Everything not on the INCLUDE list waits. If a feature is interesting but not listed, it does not ship in v0.0.1.

---

## 6. Quick Add UX requirements

(mobile-ux-designer perspective; planning only, no actual screens.)

The single most important UX property of v0.0.1 is that logging a purchase is faster than the user's resistance to doing it. If Quick Add takes more than about five seconds or more than a few taps, the habit dies and the app fails. Requirements:

- One-tap entry point. A persistent, always-reachable "+" (a primary action on Home / a floating action button) opens Quick Add directly. No menu, no intermediate screen.
- Amount-first. The amount field is focused on open, with the numeric keypad already up. The user can type the amount and save without touching anything else if defaults are acceptable.
- Merchant autocomplete. As the user types the merchant/counterparty, suggest from their recent and known merchants. Selecting one is one tap.
- Category auto-suggested from merchant history. When a known merchant is chosen, pre-fill the category from the last-used mapping (the merchant-to-category memory / CategoryRule). The user confirms or overrides; they never have to pick from scratch for a repeat merchant.
- Date defaults to today. The common case (logging a purchase as it happens) needs zero date interaction. Changing the date is available but never required.
- Save in under five seconds. The realistic happy path: open (+), type amount, tap a recent merchant (category auto-fills), save. Two or three taps plus the amount.
- Optional note only, never required.
- Sensible minimal validation: reject empty/zero/non-numeric amount inline; everything else has a default.
- Progressive disclosure: note, date change, and "create a rule for this merchant" prompts live behind the primary path, not in front of it.
- Future enhancement (NOT v0.0.1): natural-language single-line input such as "Golda 33" parsed into merchant=Golda, amount=33, category auto-suggested. Architect the entry model so this can be added later without rework, but do not build the parser now.

RTL-safe layout from the first screen (logical start/end, no hard-coded left/right) so Hebrew copy can be added later without relayout. Tone is neutral and coaching, never shaming (PRD principle 8).

---

## 7. Manual recurring expenses

Purpose: capture predictable commitments (gym, insurance, phone, streaming and other subscriptions) that the user knows about, without waiting for months of history and without a detection engine.

Firm decision for v0.0.1: recurring expense templates create PROJECTED COMMITMENTS ONLY. They do NOT auto-generate transactions.

Why this is the right call:
- Auto-generating transactions on a schedule would silently insert spend the user did not enter, then COLLIDE with the actual purchase when the user logs it (or when a future bank import lands the settlement), producing duplicates and corrupting totals. That is exactly the double-counting class of bug we are guarding against.
- A projection is honest: it says "you have committed roughly X more this month" without pretending the money already moved.
- It is far simpler to build and reason about for a solo project, and it keeps the actuals (manually entered transactions) as the single source of truth.

Model:
- A recurring expense template has a name, an amount, a cadence (monthly / weekly / yearly), and an expected next charge date.
- Cadence drives the expected-next-charge calculation. Monthly is the common case; weekly and yearly are supported for completeness.
- counts_in_projection (boolean): whether this template should be included in the projected month total on Home. Default true. The user can exclude a commitment from projection (e.g. an annual fee they account for separately) without deleting the template.
- is_active: inactive templates (cancelled subscriptions) stop contributing to projection but stay for history/record.
- v0.0.1 does NOT reconcile a projection against a matching real transaction automatically. The user sees actuals and projection clearly SEPARATED on Home (section 10); reconciliation/auto-matching is future work.

Examples: gym (monthly), car/health insurance (monthly or yearly), phone plan (monthly), streaming subscriptions (monthly). Each is a template the user adds once.

---

## 8. Bank import role after pivot

Bank import is NOT deleted and NOT the v0.0.1 core. It is repositioned as a cash-flow source, defined as:

- A CASH-FLOW overview source: income, incoming/outgoing transfers, and credit-card SETTLEMENTS (the aggregate monthly card payment), loan payments, fees. It answers "what moved through my account," not "what did I spend on."
- NOT consumer-spending categorization. A bank statement cannot tell you that you spent 33 at Golda; it only shows the lump card settlement. Consumer-spending detail comes from manual entry now, and from itemized card import later.
- An OPTIONAL, LATER source. Bank import is v0.0.2. It may appear as an optional secondary flow inside v0.0.1 only if it is trivially cheap given the existing import spec; it is never a v0.0.1 requirement.
- It MUST avoid double-counting against manual/card spending. Reuse the card-settlement exclusion flag (IMPORT_PIPELINE_SPEC section 14): any imported row classified as a credit-card settlement sets is_card_settlement = true and is EXCLUDED from consumer-spending totals and category rankings. It remains visible as cash flow so the account view stays correct, but it never inflates "spent on categories." This is what keeps manual purchases and the bank's lump settlement from being counted twice.

The existing IMPORT_PIPELINE_SPEC.md, IMPORT_SPEC_BANK_STATEMENT_HEBREW_V1.md, and the sanitized sample remain valid and unchanged in their technical content. Their POSITION changes: from "the v0.0.1 core loop" to "the v0.0.2 cash-flow source."

---

## 9. Data model impact

Conventions (firm, unchanged): signed integer minor units + currency code; UTC for metadata timestamps; calendar/purchase dates stored date-only; user_id on every user-owned row; raw transactions in SQL only, never embedded.

v0.0.1 entities:

User
- Purpose: security principal and owner of all rows.
- Required fields: id, base_currency, created_at. (email/credential optional in pure-local v0.0.1.)

Transaction (PRIMARY source is now manual)
- Purpose: the atomic spend/income line. In v0.0.1 the dominant rows are manual.
- Required fields: id, user_id, posted_date (date-only), amount_minor (signed integer), direction (debit/credit), currency, merchant_id (nullable), category_id (nullable), source (manual | bank_import), note (nullable), created_at, updated_at.
- Import-related fields are nullable in v0.0.1: account_id (nullable), import_batch_id (nullable), raw_description (nullable; for manual entries the user-typed merchant is the description), reference (nullable), operation_type (nullable), is_card_settlement (default false), dedup_hash (nullable for manual; required and unique for imported rows under unique(user_id, dedup_hash)).
- Notes: source distinguishes manual from bank_import so the two layers never blur. merchant_id and category_id stay nullable so "uncategorized" is a first-class state, never a fake Other. Manual transactions are the primary source of truth for spending; bank_import rows are cash-flow context (and settlement rows are excluded from spend per section 8).

Merchant
- Purpose: normalized payee/counterparty; anchor for rules and merchant-to-category memory.
- Required fields: id, user_id, normalized_name, raw_aliases (array/json), default_category_id (nullable), created_at.
- Notes: for manual entry, the merchant the user types is normalized here and reused via recent-merchants autocomplete.

Category
- Purpose: the consumer-spending grouping shown to the user (now live from day one).
- Required fields: id, user_id (null = system default), name, is_system, icon, parent_id (nullable, reserved).

CategoryRule
- Purpose: turns a correction or a merchant-to-category assignment into permanent learning; powers the auto-suggest in Quick Add.
- Required fields: id, user_id, match_type (merchant_exact | contains), match_value, category_id, priority, source (system | user_correction), created_at.

RecurringExpenseTemplate (NEW in v0.0.1)
- Purpose: a user-created recurring commitment that projects a future charge; does NOT auto-generate transactions (section 7).
- Required fields: id, user_id, name, merchant_id (nullable), category_id, amount_minor (signed integer), cadence (monthly | weekly | yearly), next_expected_date, is_active (bool), counts_in_projection (bool), created_at.

Account (optional / deferred for active use)
- Purpose: the money source abstraction retained for future bank/card import; not exercised by manual entry.
- Required fields (when used): id, user_id, name, type (bank/card/cash), source_format_ref, created_at.
- Notes: retained in schema so v0.0.2 bank import and later card import slot in without a rewrite. Manual transactions may carry a null account_id in v0.0.1.

ImportBatch (deferred / optional for bank import)
- Purpose: groups an import event for traceability and rollback; only relevant when bank import is enabled.
- Required fields (when used): id, user_id, account_id, source_filename_ref, row_count, imported_count, duplicate_count, uncategorized_count, status, created_at.
- Notes: not created at all by manual entry. Present in schema, used when bank_import lands (v0.0.2 or optional v0.0.1).

Deferred entirely (unchanged from prior plan): Budget (schema optional, UI deferred), MonthlySummary, RecurringExpense (DETECTED), Insight, AIConversation, AIChatMessage, FinancialKnowledgeDocument, Embedding. Even deferred entities keep their PRD shape (user_id, UTC, minor units) so adding them later is additive.

---

## 10. Dashboard impact

Home for manual-first must still pass the five-second rule: open the app and within five seconds know "how am I doing this month." It shows, in order of importance:

1. Manually entered spending this month (the actuals): one number. This is the headline.
2. Recurring commitments this month: the projected total from active templates where counts_in_projection is true, shown as a clearly separate, clearly labelled number (a commitment, not money already spent).
3. Known total this month: actual manual spend + recurring projection, presented as a combination that VISIBLY separates "spent" from "still committed" (e.g. "Spent X / Committed Y"). Never blended into one ambiguous figure.
4. Top category: the single largest spending category this month, one tap into its transactions.
5. Recent transactions: a short list of the last few entries for quick recall and correction.
6. Bank cash-flow separation: if/when bank import is enabled later, a clear label that bank cash flow is SEPARATE from manual spending, and card settlements are excluded from spend (section 8). In pure-manual v0.0.1 this line is absent.

Defending the five-second rule:
- One headline number (manual spend), one clearly separated commitment number, one top category, one short list. That is the entire surface.
- No charts. A number and a label beat any chart (PRD principle 3).
- Actuals and projection are SEPARATED, never merged, so the user is never misled about what they have actually spent. Blending them would be a correctness bug, not just a UX choice.
- The primary action on Home is the one-tap "+" (Quick Add). Everything richer (full category list, transaction list, recurring management) is one tap away, never on Home by default (progressive disclosure).

---

## 11. Version split after pivot

- v0.0.1 — Manual-first. Fast Quick Add, manual recurring templates (projected commitments only), consumer categories live, simple Home, transaction list, edit/correct. The core habit loop. (This document.)
- v0.0.2 — Bank cash-flow import. Enable the existing IMPORT_PIPELINE_SPEC bank profile as a cash-flow source: income/transfers/settlements, with the card-settlement exclusion flag preventing double-counting against manual spending.
- v0.0.3 — Credit-card import assistant / multi-file import. The itemized per-card export shape (a new profile), multi-file import, so true consumer-merchant detail can come from files too, reconciled against manual entries and against bank settlements.
- v0.1 — Insights + AI over reliable data. MonthlySummary, recurring/unusual detection, the fixed insight set, the AI coach, and RAG — now standing on real, trusted, user-entered (and imported) data. This is the PRD's full internal MVP.
- Later — Open banking / provider integration, Apple Pay/Wallet/FinanceKit, multi-user, paid SaaS. Architected for, not built (PRD section 6).

---

## 12. Risks and mitigations

- User forgets to enter expenses. The fatal risk for manual-first. Mitigation: make Quick Add genuinely sub-five-seconds (section 6) so logging is nearly frictionless; one-tap "+" always reachable; recent-merchant + auto-category so repeats are two taps. (Reminder nudges are a candidate for a LATER version, not v0.0.1, to avoid push-notification scope; design the habit, not the nag.)
- Manual entry friction. Mitigation: amount-first focus, keypad up on open, merchant autocomplete, category auto-suggested from history, today as default date. Every required interaction beyond the amount is removed from the happy path.
- Category mistakes. Mitigation: any transaction's category is editable; a correction can create/update a CategoryRule so the same merchant is right next time; uncategorized is a first-class state, never silently mis-bucketed into Other.
- Duplicates with future imports. Mitigation: manual transactions carry source = manual; imported rows carry source = bank_import with a unique dedup_hash. Card settlements imported later are excluded from spend via is_card_settlement (section 8), so the bank's lump payment never double-counts the manual purchases. Recurring templates do NOT generate transactions (section 7), removing a whole class of self-inflicted duplicates.
- Recurring expenses that change amount. Mitigation: templates are editable; the user updates the amount on the template and the projection follows. v0.0.1 uses the current template amount for projection; historical variance tracking is future work.
- Bank import double-counting (settlement vs manual spend). Mitigation: the card-settlement exclusion flag from IMPORT_PIPELINE_SPEC section 14 is retained as a first-class concept; settlement rows stay visible as cash flow but are excluded from consumer-spending totals and category rankings. Home labels bank cash flow as separate from manual spending.

---

## 13. Documents that need updating

- MVP_EXECUTION_ALIGNMENT.md — Update the v0.0.1 definition (sections 4, 5, 6, 7, 9, 11) from import-first to manual-first: Quick Add becomes the core loop; bank import moves to v0.0.2/optional; add RecurringExpenseTemplate to the kept entities; reposition the "import-first strategy" section as "data-source strategy." Keep all firm invariants. Note that this revision supersedes its v0.0.1 scope.
- DATA_SOURCE_STRATEGY.md — NEW, to be created. Replaces the "import-first" framing with the layered data-source strategy: manual entry (now), bank cash-flow import (v0.0.2), itemized card import (v0.0.3), automatic/open banking (later). Defines which source owns which data and how the card-settlement exclusion keeps layers from double-counting.
- CATEGORY_TAXONOMY.md — Update so the CONSUMER-spending taxonomy (Groceries, Eating out, Transport, Shopping, etc.) is the primary, day-one taxonomy used by manual entry, while the coarse bank cash-flow categories (Income, Transfer, Card settlement, etc.) are clearly the secondary, import-only layer. Keep the two layers separated; mark which categories are excluded from spend totals.
- DATABASE_SCHEMA_V0_0_1.md — Reflect section 9: Transaction with source and nullable import fields; add RecurringExpenseTemplate; mark Account/ImportBatch as retained-but-deferred-for-active-use; keep minor units, UTC, user_id everywhere, unique(user_id, dedup_hash) for imported rows.
- WIREFRAMES_V0_0_1.md — Reframe screens around manual-first: Quick Add as the central, sub-five-second flow; manual-first Home (actuals vs projection separated); recurring-templates management screen; transaction list/detail/edit. Bank-import screen becomes deferred/optional. RTL-safe layout retained.
- QA_TEST_PLAN_V0_0_1.md — Re-scope acceptance to manual-first: Quick Add speed/correctness, merchant-to-category memory, recurring projection math (and the firm rule that templates create NO transactions), actuals-vs-projection separation on Home, no-PII-in-logs. Keep import/settlement-exclusion tests for when v0.0.2 lands.

---

## 14. Recommendation

Proceed with manual-first. It is the smallest build that actually serves the PRD's core promise on data we can get today, and it removes the friction that would have killed daily use under import-first. The import work is not wasted — it is repositioned to v0.0.2 where it correctly serves as cash flow, not as the primary spend source.

Concrete next step: write CATEGORY_TAXONOMY.md, but with the consumer-spending taxonomy as the primary day-one layer (because manual entry needs it immediately), and the bank cash-flow categories as the clearly separated secondary import-only layer. The taxonomy is the prerequisite that both the schema (category seed data) and Quick Add (the picker and merchant-to-category memory) depend on, so it must be settled before either is built. Do not write the schema first — that would risk baking in categories the taxonomy later revises.

---

## 15. Next prompt

Send this after approving this revision:

> "Acting as the fintech-researcher agent with the product-architect agent, and using docs/PRD_V0_1.md as the long-term vision, docs/MANUAL_FIRST_MVP_REVISION.md as the governing v0.0.1 decision, and docs/IMPORT_PIPELINE_SPEC.md section 13 (bank cash-flow categories) plus section 14 (card-settlement exclusion) as input, produce docs/CATEGORY_TAXONOMY.md for manual-first v0.0.1. Make the CONSUMER-spending taxonomy (e.g. Groceries, Eating out, Transport, Shopping, Bills/Utilities, Health, etc.) the PRIMARY, day-one layer that manual Quick Add uses, and keep the coarse bank CASH-FLOW categories (Income, Incoming transfer, Outgoing transfer, Credit card payment / settlement, Loan payment, Interest / bank fee, Cash deposit / withdrawal, Other bank movement) as a clearly separated, import-only SECONDARY layer. For each category define purpose, what belongs and what does not, parent/child structure if any, system-default vs user-created handling, the uncategorized/Other policy (no dumping ground), and which categories are EXCLUDED from consumer-spending totals (card settlements and transfers). Keep it small and justified; align with the 5-second-Home principle, the manual-first scope, and the firm invariants (signed minor units, UTC metadata, user_id everywhere, raw transactions never embedded). Planning only, no code."

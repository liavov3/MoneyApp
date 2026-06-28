# Recurring Commitments (הוצאות קבועות) — MVP Spec

Status: **product/API specification amendment only.** No code, migrations,
endpoints, or UI. Aligns with the FROZEN docs (`API_CONTRACT_V0_0_1.md`,
`DATABASE_SCHEMA_V0_0_1.md`, `QA_TEST_PLAN_V0_0_1.md`, `CATEGORY_TAXONOMY.md`,
`QUICK_ADD_UX_SPEC.md`). Where this spec would touch a frozen doc, it only
*references* it and raises the change as an open question (§13) — it does not
edit frozen docs.

---

## 0. TL;DR — this feature already exists (read this first)

"Recurring commitments / הוצאות קבועות" is **not a new entity**. It is the
product/UI framing of the already-frozen **`recurring_expense_templates`**
feature:

- DB: `recurring_expense_templates` — DATABASE_SCHEMA §3.7 + §9.
- API: full CRUD at `/api/v1/recurring-templates` — API_CONTRACT §12.
- Home: `upcoming_commitments`, `committed_amount_minor`,
  `known_this_month.committed_projected_minor` — API_CONTRACT §13 (already
  implemented in `backend/app/routers/home.py`).
- Taxonomy: Layer B is literally named **`recurring_commitment`** —
  CATEGORY_TAXONOMY §5 ("Recurring commitment taxonomy").
- QA: zero-transaction + projection coverage — QA_TEST_PLAN §7, §8.

**Decision (firm, ponytail):** do NOT create a second `recurring_commitments`
table or a second `/recurring-commitments` endpoint family. That would fork the
data model, double-count on Home, and contradict frozen docs + shipped code.
Reuse the existing table/endpoints; treat "recurring commitment" as the canonical
product name for one `recurring_expense_templates` row.

This document's only NET-NEW normative content is **§6 (date advancement /
day-of-month rule)** — the one thing the frozen docs leave to "the application."
Everything else is consolidation + a naming map + QA index.

---

## 1. Naming map

| Concept | Hebrew (UI) | Product/API name (this doc) | Frozen reality (authoritative) |
|---|---|---|---|
| The feature | הוצאות קבועות | recurring commitment | `recurring_expense_templates` row; taxonomy layer `recurring_commitment` |
| Create/list/edit/remove | — | recurring-commitment endpoints | `/api/v1/recurring-templates` CRUD (API_CONTRACT §12) |
| Monthly planned total on Home | הוצאות קבועות החודש | planned commitments this month | `committed_amount_minor` / `known_this_month.committed_projected_minor` |
| Forward list on Home | חיובים קרובים | upcoming commitments | `upcoming_commitments[]` |
| Actual spend on Home | הוצאות החודש בפועל | actual spending this month | `spent_so_far_minor` / `known_this_month.spent_actual_minor` |

The English **internal keys/fields stay as frozen**. The Hebrew terms are
display-only (CATEGORY_TAXONOMY §11 principle: labels are display, keys are
identity). Whether to expose `/recurring-commitments` as an additional alias
path or rename Home fields is an **open question (§13)** requiring approval to
touch frozen docs — default is to keep frozen names.

---

## 2. Product concept

A recurring commitment is a **predictable fixed monthly obligation the user
already knows about** — rent, phone, internet, gym, insurance, streaming
(Netflix/Spotify/iCloud/ChatGPT), loans, and similar. Broader than
"subscriptions" (subscriptions is just one consumer category).

Core rule (CATEGORY_TAXONOMY §5; contract-guard "projection-only"):

> A recurring commitment is a **projection**, never an actual transaction. In
> v0.0.1/v0.0.2 it creates **zero** `transactions` rows, and it is **never**
> folded into actual-spending totals. Actuals come only from manual entry (and
> later, imports).

The user manually logs the real charge through Quick Add when it happens; the
commitment and the real charge are two separate rows and are **not**
auto-reconciled or netted (QA-07-08).

---

## 3. Scope

In scope (all already supported by the frozen table/endpoints):

1. Create a recurring commitment manually — `POST /recurring-templates`.
2. List recurring commitments — `GET /recurring-templates?active=<bool>`.
3. Update one — `PATCH /recurring-templates/{id}` (name, amount, category,
   merchant, cadence, `next_expected_date`, `counts_in_projection`, is_active,
   note).
4. Deactivate (`is_active:false`, primary "stop this") or hard-delete
   (`DELETE`, for a mistake) — API_CONTRACT §12 "Deactivate vs delete".
5. Home shows planned commitments **separately** from actual spend
   (API_CONTRACT §13).

Net-new in this doc: **§6 date-advancement rule** + the QA cases in §11.

Out of scope (§12). No auto-detection, no import matching, no notifications, no
"mark as paid", no auto transaction generation, no payment-status tracking.

---

## 4. Data model (no new table)

Use the frozen **`recurring_expense_templates`** (DATABASE_SCHEMA §3.7). It
already carries every field the MVP needs:

`id`, `user_id` (isolation, FK ON DELETE CASCADE), `name` (sensitive),
`amount_minor` (signed bigint agorot, `<> 0`), `currency` (`char_length = 3`,
default `ILS`), `category_id` (**required**, consumer-layer, FK ON DELETE
RESTRICT), `merchant_id` (nullable), `cadence` (`weekly|monthly|yearly`),
`next_expected_date` (**date-only**), `counts_in_projection` (default true),
`is_active` (default true), `note` (nullable, sensitive), `created_at`,
`updated_at`.

Decisions vs the task's "recommended model":

- **`day_of_month`: do NOT add a column.** The frozen model stores a concrete
  `next_expected_date`, which is strictly cleaner — no "what does day 31 mean in
  February" ambiguity at rest, and it directly drives the in-month projection
  query (schema §10 query 5). `day_of_month` is a **UI input only**: the client
  collects a 1–31 day, and the chosen day is realized into a concrete
  `next_expected_date` using the clamp in §6. The stored truth is always a real
  date. (ponytail: reuse the existing column; don't store a value that needs
  re-interpretation every month.)
- **No soft-delete column.** The project's convention is deactivate
  (`is_active:false`, history-preserving) + hard `DELETE` for mistakes
  (API_CONTRACT §12). There is no `deleted_at` in the schema; do not add one.
- **Cadence:** the frozen `CHECK` already allows `weekly|monthly|yearly`. MVP UI
  exposes **monthly** only; `weekly`/`yearly` are accepted by storage and
  validation today and are documented as available-but-secondary (no change, no
  restriction needed).

DB constraints to honor (all already in schema): user isolation; `amount_minor
<> 0`; cadence enum; `category_id` system-or-same-user; consumer-layer category
(enforced at the API per §5/§8 below — `bank_movement` → `422
not_consumer_category`).

---

## 5. API behavior (no new endpoints)

The endpoints in **API_CONTRACT §12** cover items 1–4 of scope exactly:

| Action | Endpoint | Notes |
|---|---|---|
| Create | `POST /api/v1/recurring-templates` | `amount` major units → agorot (§14); `category_id` required + consumer-layer; creates **zero** transactions. |
| List | `GET /api/v1/recurring-templates?active=<bool>` | principal-scoped. |
| Update | `PATCH /api/v1/recurring-templates/{id}` | all fields optional; ownership → 404. |
| Remove | `PATCH {is_active:false}` (preferred) or `DELETE …/{id}` → 204 | ownership → 404. |

Auth/ownership (contract-guard): `user_id` is **server-resolved only**; a forged
client `user_id` is ignored. Ownership mismatch / missing / malformed UUID →
**404 `not_found`** (never 403, never a leak). Errors use the standard envelope
`{ error: { code, message, request_id, field_errors? } }`.

This spec proposes **no signature changes** to §12. If the UI wants
`day_of_month` as an input convenience, it is an **additive optional request
field** on POST/PATCH that the server resolves to `next_expected_date` via §6;
flagged as open question §13 (touching the frozen contract needs approval).

---

## 6. Date semantics (NET-NEW — the one real gap)

All dates are **date-only** (`YYYY-MM-DD`), consistent with `occurred_on` and
`next_expected_date`. No timezone math; "this month" = the viewed `month`
(API_CONTRACT §13) using the same `[month_start, next_month_start)`
half-open range as transactions.

`recurring_expense_templates.next_expected_date` is the **single source of
truth** for when a commitment is due. DATABASE_SCHEMA §9 leaves advancement "to
the application"; this section defines it deterministically.

### 6.1 In-month projection (already implemented)
A commitment contributes to Home this month iff `is_active = true` AND
`counts_in_projection = true` AND `next_expected_date ∈ [month_start,
next_month_start)`. (Home read side already does this.)

### 6.2 day_of_month → concrete date (clamping)
Given an intended `day_of_month` D (1–31) and a target year/month:

```
resolved_day = min(D, days_in(target_year, target_month))
next_expected_date = date(target_year, target_month, resolved_day)
```

So D=31 → Jan 31, Feb 28 (29 in a leap year), Apr 30; D=30 → Feb 28/29; etc.
**Clamp to the last valid day; never roll into the next month.** This keeps a
"pay on the 31st" commitment landing on month-end in short months, which is the
intuitive behavior for rent/bills.

`days_in` is the calendar length of that month (leap-year aware for February).

### 6.3 Advancing after a period passes (monthly)
v0.0.1 **may simply display the stored `next_expected_date`** (schema §9). When
the app advances it (now or in a later slice), the monthly rule is:

```
intended_day = the day_of_month the user picked
               (persisted intent; in MVP, infer as the day component of the
                CURRENT next_expected_date, since there is no day_of_month column)
target = first month strictly after next_expected_date's month
next_expected_date = clamp(intended_day, target)   # §6.2
```

Clamping uses the **intended** day each cycle, not the clamped one, so a Feb-28
clamp does not permanently drag a 31st commitment to the 28th — March returns to
the 31st. (ponytail: store the date, recompute from intended day; do not store a
drifting day.)

`weekly` = +7 days; `yearly` = same month/day next year (Feb 29 → Feb 28 in
non-leap years). These are documented for completeness; MVP UI is monthly-only.

### 6.4 Manual override
The user can always PATCH `next_expected_date` to any date; that becomes the new
truth and (if the intended day were ever persisted) resets the intended day.

---

## 7. Money semantics

Per API_CONTRACT §14 and the contract-guard money rules — **unchanged**:

- Stored as **signed integer agorot** in `amount_minor` (bigint), `<> 0`.
- The API accepts a **non-negative major-unit** `amount` (Decimal/string, ≤2
  decimals; `>2 → too_many_decimals`, `0 → zero_amount`, negative →
  `negative_amount`, all 422). The server applies the sign.
- **Sign convention (frozen): a commitment amount is stored NEGATIVE**, mirroring
  an expense (API_CONTRACT §12: "sign mirrors an expense by convention").
  Projection sums use the **magnitude** (`SUM(ABS(amount_minor))`), so
  `committed_amount_minor` is a non-negative number.
- Do **not** introduce a separate "positive-storage" rule for commitments — that
  would contradict the frozen convention and the shipped Home query. (The task's
  "amount positive" intent is satisfied at the API boundary: the client sends a
  positive magnitude; storage sign is server-owned.)
- Actual-transaction sign conventions are untouched.

---

## 8. Home additions

Home **already** returns the planned/actual separation (API_CONTRACT §13,
implemented). Mapping the task's requested field names onto the frozen payload:

| Requested name | Frozen field (authoritative, keep) |
|---|---|
| `actual_spending_this_month` / הוצאות החודש בפועל | `spent_so_far_minor`, `known_this_month.spent_actual_minor` |
| `planned_recurring_commitments_this_month` / הוצאות קבועות החודש | `committed_amount_minor`, `known_this_month.committed_projected_minor` |
| `recurring_commitments_total_minor` | = `committed_amount_minor` (same number) |
| `upcoming_recurring_commitments` / חיובים קרובים | `upcoming_commitments[]` |
| `active_recurring_commitments_count` | **not currently returned** — see below |
| `next_due` items | `upcoming_commitments[]` (sorted by `next_expected_date ASC`) |

**Firm (CATEGORY_TAXONOMY §12 / contract-guard):** actual and projected are
**always distinct fields inside `known_this_month`; there is NEVER a blended
total** and planned commitments never enter any actual-spend or category total
(QA-08-01, QA-08-09).

The only candidate addition is `active_recurring_commitments_count` (count of
active templates). It is **optional and additive**; recommend **deferring** it
(the client can derive it from `GET /recurring-templates?active=true`, ponytail).
Adding it to §13 needs approval — open question §13.

---

## 9. Category behavior

Per CATEGORY_TAXONOMY §5, a commitment **reuses a Layer A consumer category**
for grouping (there are no separate Layer B category rows; `category_id` is
required). Enforced at the API: only `consumer_spending` categories; a
`bank_movement` category → `422 not_consumer_category` (QA-07-07).

Suggested mappings (from taxonomy §5 / §3):

| Commitment | Category key |
|---|---|
| Rent | `home` |
| Phone / Internet | `home` (utilities) or `subscriptions` |
| Netflix / Spotify / iCloud / ChatGPT | `subscriptions` |
| Gym | `health` |
| Insurance (health/car/home) | `health` / `transport` / `home` per the insured thing |
| Loan payment | a consumer key for the commitment view (distinct from the `bank_movement` loan row seen later in cash-flow — never summed, §5) |

Subscriptions ≠ all commitments: rent/phone/insurance/loans are commitments but
not subscriptions.

---

## 10. Privacy & logging

Per API_CONTRACT §15 / DATABASE_SCHEMA §11 / contract-guard — **unchanged**:

- **Never log** `name`, `note`, `amount`/`amount_minor`, merchant text, or the
  category text paired with an amount — including on error paths (QA-10-05).
- Home exposes `name_present` (boolean) only, never the template name
  (QA-10-11).
- **Safe to log:** `request_id`, `endpoint`, `status`, ids (`template_id`,
  `category_id`, `merchant_id`, `user_id` uuid), enums (`cadence`,
  `transaction_type`), counts, `duration_bucket`. Use `log_event` (allow-list).

---

## 11. QA cases

Existing frozen coverage to reuse as-is: **QA-07-01..09** (zero-transaction
CRUD, projection follows edits, deactivate/exclude, consumer-category enforce,
no auto-reconcile, ownership-404), **QA-08-01/08/09** (Home no-blend, empty
state, projection filter), **QA-09-06** (ownership), **QA-10-05/11** (no PII).

Net-new cases this feature needs (date/day handling — the §6 gap). IDs proposed
under a new area `RC` so they don't collide with frozen `QA-07`:

| ID | Area | Title | Setup | Expected |
|---|---|---|---|---|
| RC-01 | Create | Happy path | POST name=Netflix, amount="45.90", category=subscriptions, cadence=monthly, next_expected_date this month | 201; `amount_minor=-4590`; zero transactions created |
| RC-02 | Money | Invalid amount rejected | POST amount="0" / "-5" / "1.999" | 422 `zero_amount` / `negative_amount` / `too_many_decimals`; nothing persisted |
| RC-03 | Date | Invalid day_of_month rejected | client day_of_month=0 or 32 (or resolved invalid date) | 422 `validation_error` (invalid date) |
| RC-04 | Date | Clamp D=31 in February | intended day 31, target Feb (non-leap) | resolved `next_expected_date = Feb-28`; never Mar-03 |
| RC-04b | Date | Clamp D=31 in leap February | intended day 31, target Feb (leap) | `Feb-29` |
| RC-05 | Date | Clamp does not drift | start 2026-01-31, advance through Feb→Mar (monthly) | Feb-28 then **Mar-31** (recomputed from intended day, not 28) |
| RC-06 | Category | Must be consumer-layer | POST category=`interest_bank_fee` (bank_movement) | 422 `not_consumer_category` |
| RC-07 | Isolation | List/read/update/delete scoped to principal | template owned by B; A lists/PATCHes/DELETEs | A's list excludes B's; PATCH/DELETE B's as A → 404 |
| RC-08 | State | Active vs inactive | one active, one `is_active:false` | `?active=true` returns only active; inactive excluded from Home `committed_amount_minor` |
| RC-09 | Home | Actual vs planned separated | ₪33 expense + ₪120 active monthly template this month | `spent_so_far_minor=3300`, `committed_amount_minor=12000`; NO field = 15300 |
| RC-10 | Home | Upcoming sorted deterministically | 3 templates, different `next_expected_date` | `upcoming_commitments` ordered by `next_expected_date ASC` (tie-break `id ASC`) |
| RC-11 | Date | Month boundary | template due on month_start and on last day of month | both in-month; one in next month excluded |
| RC-12 | Invariant | No automatic transaction creation | create/patch/delete templates | `COUNT(transactions)` unchanged throughout |
| RC-13 | Privacy | Logs expose no name/note/amount | create + Home | logs carry only ids/enums/counts; `name_present` boolean only |
| RC-14 | Empty | Empty state | user with no templates | `GET /recurring-templates` → `{items:[]}`; Home `committed_amount_minor=0`, `upcoming_commitments=[]` |

---

## 12. Non-goals (explicitly NOT in MVP)

Auto-detection of recurring expenses from transaction history; bank-import
matching/reconciliation; push notifications; payment reminders; "mark as paid";
automatic transaction generation; variable-amount detection; multi-currency
beyond existing currency behavior; complex recurrence rules; weekly/yearly as
primary UI cadences (storage supports them, UI is monthly-only); shared/household
multi-user; AI insights.

---

## 13. Open questions (need approval — they touch FROZEN docs)

1. **Naming.** Keep frozen `/recurring-templates` + `committed_amount_minor`, or
   add `recurring-commitments` alias path / rename Home fields? Default: **keep
   frozen names**, use Hebrew/English product terms in UI only. Renaming changes
   shipped code (`home.py`) + API_CONTRACT §12/§13.
2. **`day_of_month` as an API input field** on POST/PATCH (resolved to
   `next_expected_date` via §6). Additive optional field; needs an edit to
   API_CONTRACT §12. Default: defer; client sends a concrete
   `next_expected_date`.
3. **`active_recurring_commitments_count` on Home** (additive §13 field).
   Default: defer (derivable from the list endpoint).
4. **Date advancement automation.** Ship §6 as the documented rule now; decide
   later whether a job/endpoint advances `next_expected_date` or the client does
   it on render (schema §9 allows display-only for v0.0.1).

---

## 14. Future work

Auto-detect recurring expenses from similar transactions; "mark as paid" that
creates a real transaction; notification/reminder system; match real
transactions against planned commitments (reconciliation, currently forbidden to
keep double-counting impossible); variable-amount commitments; first-class
weekly/yearly UI cadences; partner/shared-household view; AI-coach insights over
commitments vs actuals.

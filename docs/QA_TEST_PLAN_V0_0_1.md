# Money App — QA Test Plan (v0.0.1, manual-first)

Status: QA acceptance specification only. No test code, no implementation, no migrations. This is the pre-code acceptance matrix the implementation is built to satisfy.
Owner: qa-tester (lead), with product-architect (product invariants) and backend-api-engineer (API/database edge cases) perspectives.
Governing decision: docs/MANUAL_FIRST_MVP_REVISION.md (2026-06-14) — v0.0.1 is manual-first; fast Quick Add is the primary loop.
Sources of truth (all read, treated as FROZEN): docs/PRD_V0_1.md, docs/MANUAL_FIRST_MVP_REVISION.md, docs/CATEGORY_TAXONOMY.md, docs/MERCHANT_NORMALIZATION_SPEC.md, docs/QUICK_ADD_UX_SPEC.md, docs/DATABASE_SCHEMA_V0_0_1.md, docs/API_CONTRACT_V0_0_1.md.
Date: 2026-06-14

---

## 0. Scope & invariants under test

This plan is a practical, table-driven pass/fail acceptance matrix for the seven active tables (`users`, `transactions`, `merchants`, `merchant_aliases`, `categories`, `category_rules`, `recurring_expense_templates`) and the v0.0.1 REST surface (`/categories`, `/merchants/suggestions`, `/merchants/recent`, `/transactions/quick-add`, `/transactions`, `/transactions/{id}`, `/transactions/{id}/categorize`, `/category-rules`, `/merchants/{id}/aliases`, `/recurring-templates`, `/home`). It is implementation-oriented: each row is an acceptance case an engineer builds to.

The non-negotiable correctness invariants this plan exists to guarantee (all P0):

- Money correctness — decimal→agorot exact; >2 decimals REJECTED (never silently rounded); zero/negative expense rejected; sign applied server-side from `transaction_type`; ILS default.
- No silent merge — exact/alias_exact/normalized_exact auto-select only; recent_suggestion/contains suggest only; cross-script (Golda/גולדה) and fuzzy_possible NEVER auto-merge.
- Recurring = ZERO transactions — templates project only; creating/editing a template never writes a `transactions` row.
- Home never blends — `spent_so_far_minor` (actual) and `committed_amount_minor` / `known_this_month.{spent_actual_minor, committed_projected_minor}` are DISTINCT fields; no blended total anywhere.
- Ownership mismatch → 404 (not 403) — no existence leak.
- No PII in logs — never log merchant text/amount/note/raw input/correction content; only request id, endpoint, status, duration bucket, validation error code enum, confidence-level enum, row counts.
- Save-first / enrich-after — Quick Add persists first; `rule_prompt`/`alias_suggestion`/duplicate/large-amount are non-blocking response data, never gates.

### Legend — Priority / Must-pass

| Priority | Meaning |
|---|---|
| P0 | MUST-PASS. Blocking for v0.0.1 ship. A failure here ships a money-correctness, double-counting, privacy, or authorization defect. Cannot ship red. |
| P1 | Important. Required for a trustworthy build; fix before ship unless explicitly waived by product-architect with a logged reason. |
| P2 | Nice-to-have. Polish / edge hardening; may slip to a fast-follow without blocking ship. |

ID scheme: `QA-<area>-<n>`. Areas: 01 Quick Add save-first, 02 money parsing, 03 merchant matching, 04 aliases/409, 05 rule update-not-stack, 06 categorize/apply_to_existing, 07 recurring zero-transactions, 08 Home no-blend, 09 ownership-404, 10 no-PII-logs, 11 generic errors, 12 transaction list/edit/delete, 13 categories/filtering, 14 duplicate/large save-then-warn.

### Contradictions found

No blocking contradictions found. The seven upstream docs are mutually consistent on every invariant under test (signed agorot + ILS default; nullable `merchant_id`/`category_id`; save-first; recurring projection-only; Home separation; 22 seeded categories with `included_in_committed_projection=false`; ownership 404; no-PII logging). Two harmless naming reconciliations were already resolved upstream and are honored here, not re-litigated: canonical bank keys are `interest_bank_fee` and `cash_deposit_withdrawal` (DATABASE_SCHEMA §7), and the single date-only field is `occurred_on` (no `occurred_at` timestamp; DATABASE_SCHEMA §5). One minor cross-doc note for the engineer (not a blocker): API_CONTRACT §8 step 3 says the server does not silently invent a category the client did not send, while QUICK_ADD_UX implies merchant selection auto-fills a suggestion — both are satisfied if the client echoes the suggested `category_id` it wants saved; tests QA-01-04 and QA-13-06 pin this down.

---

## 1. Quick Add save-first behavior

Endpoint: `POST /transactions/quick-add`. Schema: `transactions` (nullable `merchant_id`/`category_id`, `occurred_on DEFAULT CURRENT_DATE`, `source='manual'`, `transaction_type='expense'`).

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-01-01 | Quick Add | Amount-only save (Mode A) is first-class | Body `{ "amount": 33 }`, no merchant, no category | POST quick-add | 201; `transaction.amount_minor=-3300`, `merchant_id=null`, `category_id=null`, `occurred_on=today`, `source=manual`, `transaction_type=expense`; `rule_prompt.offer=false`; row counts in spend | P0 |
| QA-01-02 | Quick Add | Amount + merchant (Mode B), category resolved from memory | Merchant "Golda" exists with recent memory `eating_out`; body `{ "amount": "33", "merchant_input": "Golda" }` | POST quick-add | 201; `merchant_id` set, `category_id=eating_out`, `category_suggestion.source=recent_memory`; `rule_prompt.offer=true` (no trusted rule yet) | P0 |
| QA-01-03 | Quick Add | Amount + merchant + category (Mode C) | Body `{ "amount": "33.50", "merchant_id": "<Golda>", "category_id": "<eating_out>" }` | POST quick-add | 201; fully categorized; `amount_minor=-3350`; `category_suggestion.source=user_choice`; `rule_prompt.offer=true` | P0 |
| QA-01-04 | Quick Add | Server does not invent a category the client did not send | Merchant resolves but body omits `category_id` and sends no accepted suggestion | POST quick-add | 201; saved `category_id=null` (uncategorized); `category_suggestion` returned as suggestion only, not persisted | P1 |
| QA-01-05 | Quick Add | Merchant optional — never blocks save | Body `{ "amount": 50 }` | POST quick-add | 201; `merchant_id=null`; appears in uncategorized review; no error | P0 |
| QA-01-06 | Quick Add | Category optional — never blocks save | Body `{ "amount": 50, "merchant_input": "NewPlace" }`, no rule/memory | POST quick-add | 201; new merchant created (`none` path), `category_id=null`; save succeeds | P0 |
| QA-01-07 | Quick Add | Date defaults to today when omitted | Body omits `occurred_on`; server date = 2026-06-14 | POST quick-add | 201; `occurred_on="2026-06-14"` | P0 |
| QA-01-08 | Quick Add | Backdating allowed | Body `{ "amount": 20, "occurred_on": "2026-05-30" }` | POST quick-add | 201; `occurred_on="2026-05-30"`; buckets into May | P1 |
| QA-01-09 | Quick Add | Save never blocked by enrichment — rule_prompt is suggestion not gate | Mode B save where rule_prompt would offer | POST quick-add | 201 returned in one call; `rule_prompt.offer=true` is data on the 201; no second confirm call required to persist the transaction | P0 |
| QA-01-10 | Quick Add | alias_suggestion returned as suggestion not gate | `merchant_input="גולדה"` while "Golda" exists | POST quick-add | 201; a NEW merchant created (no merge); `alias_suggestion` non-null with candidate/new merchant ids; transaction already saved | P0 |
| QA-01-11 | Quick Add | rule_prompt suppressed for amount-only | Body `{ "amount": 33 }` | POST quick-add | 201; `rule_prompt.offer=false`; no merchant to key a rule to | P1 |
| QA-01-12 | Quick Add | rule_prompt suppressed for one-off other_spending and generic/transfer merchants | `merchant_input="Paybox"` (generic) OR category `other_spending` | POST quick-add | 201; `rule_prompt.offer=false` (MERCHANT_NORMALIZATION §10/§12 guard) | P1 |
| QA-01-13 | Quick Add | client never supplies user_id / amount_minor / sign | Body includes `"user_id"`, `"amount_minor"`, or negative `amount` for expense | POST quick-add | `user_id`/`amount_minor` ignored (server-resolved); negative expense → 422 `negative_amount` | P0 |

---

## 2. agorot / money parsing and rounding rejection

Boundary: API_CONTRACT §14. Schema: `amount_minor bigint`, `CHECK (amount_minor <> 0)`, `currency` len 3. Sign convention: expense stored NEGATIVE, income/refund POSITIVE.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-02-01 | Money | Whole shekels → agorot | `{ "amount": 33 }` | POST quick-add | `amount_minor = -3300` exactly | P0 |
| QA-02-02 | Money | One decimal place | `{ "amount": "33.5" }` | POST quick-add | `amount_minor = -3350` exactly | P0 |
| QA-02-03 | Money | Two decimal places | `{ "amount": "33.50" }` | POST quick-add | `amount_minor = -3350` exactly | P0 |
| QA-02-04 | Money | Reject >2 decimals — NEVER silently round | `{ "amount": "33.555" }` | POST quick-add | 422 `validation_error`, field `amount` code `too_many_decimals`; NOTHING persisted; NOT rounded to 3356 or 3355 | P0 |
| QA-02-05 | Money | Reject >2 decimals via JSON number | `{ "amount": 33.999 }` | POST quick-add | 422 `too_many_decimals`; not rounded to -3400 | P0 |
| QA-02-06 | Money | Reject zero | `{ "amount": 0 }` | POST quick-add | 422 `zero_amount`; nothing persisted | P0 |
| QA-02-07 | Money | Reject negative for expense | `{ "amount": -33, "transaction_type": "expense" }` | POST quick-add | 422 `negative_amount`; client never sends minus | P0 |
| QA-02-08 | Money | Reject non-numeric | `{ "amount": "abc" }` | POST quick-add | 422 `validation_error` on `amount` | P0 |
| QA-02-09 | Money | Reject empty/missing amount | `{ }` (no amount) | POST quick-add | 422 `empty_amount`; amount is the one required field | P0 |
| QA-02-10 | Money | Signed-by-type: income stored positive | `{ "amount": 5000, "transaction_type": "income" }` | POST quick-add | `amount_minor = +500000`; positive | P0 |
| QA-02-11 | Money | Signed-by-type: refund stored positive | `{ "amount": "12.00", "transaction_type": "refund" }` | POST quick-add | `amount_minor = +1200`; nets against category, not spend | P1 |
| QA-02-12 | Money | ILS default when currency omitted | `{ "amount": 33 }` | POST quick-add | `currency="ILS"` | P0 |
| QA-02-13 | Money | Invalid currency rejected | `{ "amount": 33, "currency": "SHEKEL" }` | POST quick-add | 422 `invalid_currency` (len != 3) | P1 |
| QA-02-14 | Money | Very small value (1 agora) | `{ "amount": "0.01" }` | POST quick-add | `amount_minor = -1` exactly | P1 |
| QA-02-15 | Money | Very large value within bigint | `{ "amount": "99999999.99" }` | POST quick-add | `amount_minor = -9999999999`; no overflow, exact (note: also triggers QA-14 large-amount warning, still 201) | P1 |
| QA-02-16 | Money | Binary-float safety on the wire | `{ "amount": 0.1 }` and `{ "amount": 0.3 }` | POST quick-add (x2) | `-10` and `-30` exactly; no `0.30000000004` artifact; fixed-point parse, not binary float | P0 |
| QA-02-17 | Money | Trailing-zero normalization | `{ "amount": "33.10" }` vs `{ "amount": "33.1" }` | POST quick-add (x2) | both → `-3310`; equal | P2 |

---

## 3. merchant matching and NO silent cross-script merge

Endpoints: `GET /merchants/suggestions`, resolution in `POST /transactions/quick-add`. Schema: `merchants.UNIQUE(user_id, normalized_merchant_name)`, deterministic normalization (MERCHANT_NORMALIZATION §4), no fuzzy/ML index.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-03-01 | Merchant | Exact match auto-selects | Merchant "Wolt" exists; query=`Wolt` | GET suggestions | `query_confidence=exact`; `auto_select_merchant_id` set; no new merchant | P0 |
| QA-03-02 | Merchant | normalized_exact (case/whitespace) auto-selects | "Golda" exists; query=`golda ` | GET suggestions | `query_confidence=normalized_exact`; `auto_select_merchant_id` set; same merchant | P0 |
| QA-03-03 | Merchant | alias_exact auto-selects | "גולדה" is a user_confirmed alias of "Golda"; query=`גולדה` | GET suggestions | `confidence=alias_exact`, `matched_via=alias`; `auto_select_merchant_id`=Golda | P0 |
| QA-03-04 | Merchant | recent_suggestion suggests only (no auto-select) | recent merchants incl. "Golda"; query=`gol` | GET suggestions | item `confidence=recent_suggestion`, `requires_confirmation=false`, but `auto_select_merchant_id=null` (tap required) | P0 |
| QA-03-05 | Merchant | contains suggests, never auto-merges | "Wolt" exists; query=`WOLT TEL AVIV` | GET suggestions | item `confidence=contains`, `requires_confirmation=true`; `auto_select_merchant_id=null` | P0 |
| QA-03-06 | Merchant | Cross-script NEVER silently merges | "Golda" exists; quick-add `merchant_input="גולדה"` | POST quick-add | NEW separate merchant created; `alias_suggestion` returned; no auto-link; Golda's transactions unchanged | P0 |
| QA-03-07 | Merchant | fuzzy_possible behaves as none (no fuzzy merge) | "Golda" exists; `merchant_input="Goldaa"` (typo) | POST quick-add | treated as `none`; new merchant "Goldaa" created; never merged into "Golda" | P0 |
| QA-03-08 | Merchant | Branch may matter — suggest, not merge | "Golda Givatayim" exists; query=`Golda Dizengoff` | GET suggestions | `contains` suggestion with `requires_confirmation=true`; two remain distinct unless user confirms | P1 |
| QA-03-09 | Merchant | Generic/transfer-like names not auto-anchored | `merchant_input="Bit"` / "Paybox" / "ATM" | POST quick-add | merchant stored low-trust; no rule prompt; never anchors a contains rule | P1 |
| QA-03-10 | Merchant | none path creates new merchant on save | `merchant_input="BrandNewCafe"` (nothing matches) | POST quick-add | 201; new merchant created; raw input stored as first alias; `category_id=null` unless picked | P0 |
| QA-03-11 | Merchant | Hebrew preserved, English case-folded | `merchant_input="שופרסל"` then `"SHUFERSAL"` | POST quick-add (x2) | `שופרסל` key preserves Hebrew; `shufersal` key lower-cased; they do NOT share a key (separate merchants until aliased) | P0 |
| QA-03-12 | Merchant | Invisible/bidi chars stripped from key, preserved in display | `merchant_input` with U+200E embedded in "Golda" | POST quick-add | normalized key matches plain "golda" (auto-select if exists); display preserves typed text | P1 |
| QA-03-13 | Merchant | No duplicate rival merchant for same normalized key | Two quick-adds `merchant_input="Aroma"` and `"aroma "` | POST quick-add (x2) | second resolves to the SAME merchant (normalized_exact); `UNIQUE(user_id, normalized_merchant_name)` holds | P0 |
| QA-03-14 | Merchant | suggested_category_source reflects precedence ladder | merchant with a user_correction merchant_exact rule | GET suggestions | `suggested_category_source=user_correction_merchant_exact` (the resolving level) | P1 |

---

## 4. aliases and 409 conflict behavior

Endpoint: `POST /merchants/{id}/aliases`. Schema: `merchant_aliases.UNIQUE(user_id, normalized_alias_key)`, `source` default `user_confirmed`.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-04-01 | Aliases | Confirm creates user_confirmed alias | merchant "Golda" exists; body `{ "alias_text": "גולדה" }` | POST /merchants/{Golda}/aliases | 201; `alias.source=user_confirmed`; alias_text NOT echoed verbatim | P0 |
| QA-04-02 | Aliases | After confirm, variant auto-selects | alias from QA-04-01 exists; query=`גולדה` | GET suggestions | `confidence=alias_exact`; auto-selects Golda; Golda's merchant_exact rule fires for it | P0 |
| QA-04-03 | Aliases | 409 when key already resolves elsewhere | `normalized_alias_key` for the text already points to a DIFFERENT merchant | POST /merchants/{id}/aliases | 409 `conflict`; message "This conflicts with existing data."; no silent re-point | P0 |
| QA-04-04 | Aliases | Absorb duplicate merchant re-points transactions | `गולדה` became its own merchant with 2 txns; body `{ "alias_text":"גולדה", "absorb_merchant_id":"<dup>" }` | POST /merchants/{Golda}/aliases | 201; `repointed_transaction_count=2`; dup merchant removed; transactions now point to Golda | P1 |
| QA-04-05 | Aliases | System never creates a user_confirmed alias on its own | quick-add with cross-script input, no explicit alias call | POST quick-add | NO `user_confirmed` alias created; only `alias_suggestion` returned; merge requires this explicit endpoint | P0 |
| QA-04-06 | Aliases | Ownership: alias on another principal's merchant → 404 | merchant `{id}` owned by user B | POST /merchants/{id}/aliases as user A | 404 `not_found` (not 403) | P0 |
| QA-04-07 | Aliases | alias_text never logged | any alias confirm | POST /merchants/{id}/aliases | logs carry only ids/enums; assert no `alias_text`/`normalized_alias_key` in any log line | P0 |
| QA-04-08 | Aliases | Validation: empty alias_text rejected | body `{ "alias_text": "" }` | POST /merchants/{id}/aliases | 422 `validation_error` | P1 |

---

## 5. category rule update-not-stack

Endpoints: `POST /category-rules`, `POST /transactions/{id}/categorize`. Schema: `category_rules.UNIQUE(user_id, match_type, match_value)`, `source` ∈ {system, user_correction}.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-05-01 | Rules | First correction creates one rule | merchant "Wolt"; categorize→eating_out, promote_to_rule | POST categorize | 200; one `category_rules` row, `source=user_correction`, `match_type=merchant_exact` | P0 |
| QA-05-02 | Rules | Second correction UPDATES not stacks | rule "wolt"→eating_out exists; correct same merchant→shopping | POST categorize promote | 200; STILL one row for `(user_id, merchant_exact, wolt)`, `category_id=shopping`, `updated_at` refreshed; NOT two rows | P0 |
| QA-05-03 | Rules | Third correction updates again | continue QA-05-02; correct→subscriptions | POST categorize promote | one row, `category_id=subscriptions`; count of rules for that merchant = 1 | P0 |
| QA-05-04 | Rules | user_correction outranks system | system contains "wolt"→eating_out AND user merchant_exact "wolt"→shopping | GET suggestions for "Wolt" | suggested category = shopping (user_correction merchant_exact wins ladder) | P0 |
| QA-05-05 | Rules | One merchant → one category at a time | repeat conflicting corrections for one merchant | POST categorize promote (x N) | always exactly one active exact rule per merchant; no rival rows | P0 |
| QA-05-06 | Rules | Tie within level broken by most-recently-updated | two same-priority same-level candidates | resolve suggestion | newer `updated_at` wins | P2 |
| QA-05-07 | Rules | Generic/short contains fragment rejected as rule value | promote with `match_type=merchant_contains`, fragment "cafe" | POST categorize / POST category-rules | 422 `validation_error` (generic-token denylist / min length) | P1 |
| QA-05-08 | Rules | Direct rule upsert derives match_value from merchant_id | `POST /category-rules { match_type:merchant_exact, merchant_id, category_id }` | POST category-rules | 201/200; server derives `match_value` from merchant normalized name; client never sends normalized text | P1 |
| QA-05-09 | Rules | match_value never echoed verbatim | any rule create/update response | inspect response | `match_value_present: true` only; raw fragment/merchant text NOT in body | P0 |
| QA-05-10 | Rules | match_type/match_value not editable via PATCH | `PATCH /category-rules/{id}` with new match_value | PATCH | only `category_id`/`priority`/`is_active` change; key immutable (deactivate-and-recreate) | P2 |

---

## 6. categorize endpoint with apply_to_existing default false

Endpoint: `POST /transactions/{id}/categorize`. Default `apply_to_existing=false` (going-forward only).

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-06-01 | Categorize | Categorize one transaction, no rule | `{ "category_id": "<eating_out>" }` (promote_to_rule omitted/false) | POST categorize | 200; this transaction `category_id` updated; `rule=null`; no other rows changed | P0 |
| QA-06-02 | Categorize | Promote creates rule, existing NOT bulk-updated by default | 3 prior "Wolt" txns uncategorized; `{ category_id, promote_to_rule:true }` (apply_to_existing default false) | POST categorize | 200; rule created; only the target transaction changed; `applied_to_existing_count=0`; the 3 priors UNCHANGED | P0 |
| QA-06-03 | Categorize | apply_to_existing=true bulk-updates explicitly | same 3 priors; `{ category_id, promote_to_rule:true, apply_to_existing:true }` | POST categorize | 200; the 3 priors re-categorized; `applied_to_existing_count=3` | P0 |
| QA-06-04 | Categorize | Non-consumer category rejected | `{ "category_id": "<income>" }` | POST categorize | 422 `not_consumer_category`; nothing changed | P0 |
| QA-06-05 | Categorize | Promote requires a merchant | transaction with `merchant_id=null`; promote_to_rule:true | POST categorize | 422 `unknown_merchant` (no merchant to key a rule to); category may still set on the txn only if promote omitted | P1 |
| QA-06-06 | Categorize | Going-forward: future quick-add picks up the new rule | after QA-06-02 rule exists; new "Wolt" quick-add | POST quick-add | suggested/saved category follows the rule | P1 |
| QA-06-07 | Categorize | Ownership: categorize another principal's txn → 404 | txn owned by user B | POST categorize as user A | 404 `not_found` | P0 |
| QA-06-08 | Categorize | applied_to_existing_count scoped to principal only | user A and user B both have "Wolt" txns; A applies bulk | POST categorize apply_to_existing | only A's txns updated; B's untouched; count reflects A only | P0 |

---

## 7. recurring templates create ZERO actual transactions

Endpoints: `/recurring-templates` CRUD. Schema: `recurring_expense_templates` (projection-only); NO trigger/job writes `transactions`.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-07-01 | Recurring | Create template writes ZERO transactions | baseline `COUNT(transactions)=N`; POST template (Gym, health, monthly, this month) | POST /recurring-templates | 201 template row; `COUNT(transactions)` STILL = N | P0 |
| QA-07-02 | Recurring | PATCH amount writes ZERO transactions; projection follows | template exists; PATCH amount 120→150 | PATCH /recurring-templates/{id} | 200; no new transaction; Home `committed_amount_minor` reflects new amount | P0 |
| QA-07-03 | Recurring | Deactivate writes ZERO transactions; drops from projection | active template; PATCH `is_active:false` | PATCH | 200; no transaction; template excluded from `committed_amount_minor`; row retained for history | P0 |
| QA-07-04 | Recurring | counts_in_projection=false excludes without deleting | PATCH `counts_in_projection:false` | PATCH | 200; template kept; excluded from projection sum | P1 |
| QA-07-05 | Recurring | Hard delete removes template, no transaction side effects | DELETE template | DELETE /recurring-templates/{id} | 204; template gone; `COUNT(transactions)` unchanged | P1 |
| QA-07-06 | Recurring | GET active filter | several active + inactive templates; `?active=true` | GET /recurring-templates | only active returned | P2 |
| QA-07-07 | Recurring | Template category must be consumer-layer | POST template `category_id=<credit_card_settlement>` | POST | 422 `not_consumer_category` | P1 |
| QA-07-08 | Recurring | No reconciliation: template + matching real txn coexist | template Gym 120 this month AND a manual Gym 120 expense | POST both | both exist; actual counts in spend, template counts in projection; they are NOT auto-merged or netted | P0 |
| QA-07-09 | Recurring | Ownership: PATCH another principal's template → 404 | template owned by user B | PATCH as user A | 404 `not_found` | P0 |
| QA-07-10 | Recurring | Template name/note/amount never logged | any create/patch | inspect logs | only ids/enums/counts; no `name`/`note`/amount | P0 |

---

## 8. GET /home never blends actual vs projected

Endpoint: `GET /home`. Schema §10 queries. Spend filter: `source=manual` AND `transaction_type=expense` AND `is_card_settlement=false` AND in-month AND (`category_id IS NULL` OR `included_in_actual_spending=true`).

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-08-01 | Home | Actual and projected are DISTINCT fields, never blended | one ₪33 eating_out expense + one active ₪120 health template (projects this month) | GET /home | `spent_so_far_minor=3300`; `committed_amount_minor=12000`; `known_this_month.spent_actual_minor=3300`, `.committed_projected_minor=12000`; NO field equals 15300 | P0 |
| QA-08-02 | Home | No single blended total anywhere in payload | same as QA-08-01 | GET /home; scan all numeric fields | no key in the response holds actual+projected summed | P0 |
| QA-08-03 | Home | Uncategorized expense counts in spend but flagged | one ₪50 amount-only expense | GET /home | included in `spent_so_far_minor`; `uncategorized_count=1`; recent item `is_uncategorized=true` | P0 |
| QA-08-04 | Home | Uncategorized excluded from top_category and category_totals | uncategorized + categorized expenses | GET /home | `top_category` and `category_totals` contain only real categories; uncategorized not ranked | P0 |
| QA-08-05 | Home | Settlement/import rows excluded by is_card_settlement | (future-guard) a row with `is_card_settlement=true` or `source!=manual` | GET /home | excluded from `spent_so_far_minor` and `category_totals` by construction | P0 |
| QA-08-06 | Home | top_category is the largest Layer A category | groceries ₪780 > eating_out ₪510 | GET /home | `top_category.category_key=groceries`, `total_minor=78000` | P1 |
| QA-08-07 | Home | category_totals ranked DESC, magnitudes | several categories | GET /home | totals are non-negative magnitudes, ordered DESC | P1 |
| QA-08-08 | Home | Empty month — empty states | no transactions, no templates this month | GET /home | `spent_so_far_minor=0`, `top_category=null`, `category_totals=[]`, `uncategorized_count=0`, `committed_amount_minor=0` | P0 |
| QA-08-09 | Home | committed only counts active + counts_in_projection + in-month | mix of inactive / excluded / future-month templates | GET /home | only active, projecting, in-month templates summed into `committed_amount_minor` | P0 |
| QA-08-10 | Home | spent_so_far_minor returned as non-negative magnitude | expenses stored negative | GET /home | `spent_so_far_minor` positive integer (magnitude), not negative | P0 |
| QA-08-11 | Home | income/refund do not inflate spend | one income +5000, one refund +12 | GET /home | excluded from `spent_so_far_minor` (filter `transaction_type=expense`); refund nets its category, not headline spend | P1 |
| QA-08-12 | Home | Month filter buckets by occurred_on | backdated May expense + June expense; `?month=2026-06` | GET /home | only June counted | P1 |
| QA-08-13 | Home | No Layer C cash_flow field in pure-manual v0.0.1 | manual-only data | GET /home | no `cash_flow` key present | P2 |

---

## 9. ownership mismatch returns 404 not 403

API_CONTRACT §5: ownership mismatch → 404 (no existence leak). Applies to transaction/merchant/template/rule/alias.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-09-01 | Ownership | GET another principal's transaction → 404 | txn owned by user B | GET /transactions/{id} as A | 404 `not_found`; identical to a missing id | P0 |
| QA-09-02 | Ownership | PATCH another principal's transaction → 404 | txn owned by B | PATCH as A | 404 `not_found` | P0 |
| QA-09-03 | Ownership | DELETE another principal's transaction → 404 | txn owned by B | DELETE as A | 404 `not_found` | P0 |
| QA-09-04 | Ownership | Categorize another principal's transaction → 404 | txn owned by B | POST categorize as A | 404 `not_found` | P0 |
| QA-09-05 | Ownership | Alias on another principal's merchant → 404 | merchant owned by B | POST /merchants/{id}/aliases as A | 404 `not_found` | P0 |
| QA-09-06 | Ownership | PATCH/DELETE another principal's template → 404 | template owned by B | PATCH/DELETE as A | 404 `not_found` | P0 |
| QA-09-07 | Ownership | PATCH another principal's rule → 404 | rule owned by B | PATCH /category-rules/{id} as A | 404 `not_found` | P0 |
| QA-09-08 | Ownership | 404 message reveals nothing | any of the above | inspect body | generic "Resource not found."; no id-derived detail, no "exists but forbidden" hint | P0 |
| QA-09-09 | Ownership | Distinguish ownership-404 from blocked-op-403 | mutate a system category | attempt mutate | 403 `unsupported_operation` (deliberately blocked op), NOT 404 — confirms the two codes are used correctly | P1 |
| QA-09-10 | Ownership | Missing principal → 401 | no/invalid dev token | any endpoint | 401 `unauthorized`; no resource returned | P0 |
| QA-09-11 | Ownership | Client cannot name another user_id | body/query attempts `user_id` | any write | ignored; server-resolved principal used; no cross-user write path | P0 |

---

## 10. no PII in logs

API_CONTRACT §15, DATABASE_SCHEMA §11. Safe log shape: `{ request_id, endpoint, status, duration_bucket, validation_error_code?, confidence_level?, row_count? }`.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-10-01 | Logs | Quick-add logs no merchant text/amount/note | quick-add with merchant_input + note + amount | inspect all logs (request/response/trace/error) | NO `merchant_input`/`raw_merchant_input`/`note`/`amount`/`amount_minor` text anywhere | P0 |
| QA-10-02 | Logs | Suggestions logs no query/display_name | GET suggestions Hebrew query | inspect logs | only `confidence_level` enum + item count; no `query`/`display_name` | P0 |
| QA-10-03 | Logs | Categorize logs no match_value/category text paired with amount | promote rule | inspect logs | only ids/enums; no `match_value`, no category text tied to amount/merchant | P0 |
| QA-10-04 | Logs | Alias logs no alias_text | confirm alias | inspect logs | no `alias_text`/`normalized_alias_key` | P0 |
| QA-10-05 | Logs | Template logs no name/note/amount | create template | inspect logs | no `name`/`note`/amount | P0 |
| QA-10-06 | Logs | users.email / credential_ref / dev token never logged | any authenticated request | inspect logs | `user_id` uuid only; no email/token/credential_ref | P0 |
| QA-10-07 | Logs | Validation errors log code enum only, not the bad value | submit `amount=33.555` | inspect logs | `validation_error_code=too_many_decimals`; the value `33.555` NOT logged | P0 |
| QA-10-08 | Logs | Confidence level logged as enum name only | cross-script suggestion | inspect logs | `confidence_level=none`/`contains` name only; never the producing text | P0 |
| QA-10-09 | Logs | Duration bucket present, used to verify 5s goal | quick-add | inspect logs | `duration_bucket` ∈ {`<2s`,`2-5s`,`>5s`}; no raw timing tied to content | P1 |
| QA-10-10 | Logs | Stack traces / 500s carry no content | force `internal_error` | inspect logs | generic; no body field content, no stack with PII | P0 |
| QA-10-11 | Logs | Home payload logging restraint | GET /home | inspect logs | only counts/ids; `name_present` boolean honored (no template names on Home payload either) | P1 |

---

## 11. generic error responses

API_CONTRACT §5 envelope: `{ error: { code, message, request_id, field_errors? } }`. Messages content-free.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-11-01 | Errors | Envelope shape stable | any 422 | POST quick-add bad amount | body has `error.code`, `error.message`, `error.request_id`, `error.field_errors[]` | P0 |
| QA-11-02 | Errors | validation_error → 422 with field codes | `amount=0` | POST quick-add | 422 `validation_error`; `field_errors[0]={field:amount, code:zero_amount}`; message generic "One or more fields are invalid." | P0 |
| QA-11-03 | Errors | not_found → 404 generic | missing/foreign id | GET /transactions/{id} | 404 `not_found`; "Resource not found."; no echoed detail | P0 |
| QA-11-04 | Errors | conflict → 409 generic | alias key already resolves elsewhere | POST /merchants/{id}/aliases | 409 `conflict`; "This conflicts with existing data." | P0 |
| QA-11-05 | Errors | unauthorized → 401 generic | no token | any | 401 `unauthorized`; "Authentication required." | P0 |
| QA-11-06 | Errors | unsupported_operation → 403 | mutate system category / deferred stub | attempt | 403 `unsupported_operation`; "This operation is not supported." | P1 |
| QA-11-07 | Errors | backend_unavailable → 503, nothing saved | DB down | POST quick-add | 503 `backend_unavailable`; message says entry not saved, retry; NO partial write | P0 |
| QA-11-08 | Errors | internal_error → 500, no leak | unexpected exception | any | 500 `internal_error`; "Something went wrong. Try again."; no stack/content | P0 |
| QA-11-09 | Errors | No message ever contains amount/merchant/note | trigger each error type | inspect messages | every `message` is generic and content-free | P0 |
| QA-11-10 | Errors | request_id present and matches safe log | any error | compare body + log | same `request_id` traceable without content | P1 |
| QA-11-11 | Errors | Clients branch on code not message | each error | inspect | `code` is a stable snake_case enum | P1 |

---

## 12. transaction list / edit / delete behavior

Endpoints: `GET /transactions`, `GET /transactions/{id}`, `PATCH /transactions/{id}`, `DELETE /transactions/{id}`.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-12-01 | Txn list | List by month buckets by occurred_on | May + June txns; `?month=2026-06` | GET /transactions | only June rows; ordered `occurred_on DESC, created_at DESC` | P0 |
| QA-12-02 | Txn list | Filter by category_id | mixed categories; `?category_id=<eating_out>` | GET /transactions | only eating_out rows | P1 |
| QA-12-03 | Txn list | Uncategorized filter | mix incl. null category; `?uncategorized=true` | GET /transactions | only `category_id=null` rows | P1 |
| QA-12-04 | Txn list | category_id + uncategorized mutually exclusive | both params set | GET /transactions | 422 `validation_error` | P1 |
| QA-12-05 | Txn list | Cursor pagination stable under inserts | >limit rows; page 1, insert new top row, page 2 via cursor | GET /transactions x2 | no duplicate/skipped rows; `next_cursor` opaque; null at end | P1 |
| QA-12-06 | Txn list | limit bounds | `?limit=500` | GET /transactions | clamped to max 100 (or 422); default 50 when omitted | P2 |
| QA-12-07 | Txn edit | PATCH amount re-normalizes sign | expense; `{ "amount": "30.00" }` | PATCH | `amount_minor=-3000`; sign recomputed server-side | P0 |
| QA-12-08 | Txn edit | PATCH category to consumer category | `{ "category_id": "<shopping>" }` | PATCH | 200; category updated; may return `rule_prompt` but creates NO rule | P0 |
| QA-12-09 | Txn edit | PATCH category does NOT auto-create a rule | `{ "category_id": "<shopping>" }` | PATCH then inspect rules | no `category_rules` row created; rule promotion only via categorize endpoint | P0 |
| QA-12-10 | Txn edit | PATCH non-consumer category rejected | `{ "category_id": "<income>" }` | PATCH | 422 `not_consumer_category` | P0 |
| QA-12-11 | Txn edit | PATCH clear merchant / clear category | `{ "merchant_id": null }` / `{ "category_id": null }` | PATCH | merchant-less / uncategorized; both first-class | P1 |
| QA-12-12 | Txn edit | PATCH note + date | `{ "note":"split", "occurred_on":"2026-06-13" }` | PATCH | updated; note never logged | P1 |
| QA-12-13 | Txn edit | Remains actual spending unless transaction_type changed | PATCH amount/merchant/category/note/date | PATCH; GET /home | still counts in `spent_so_far_minor` | P0 |
| QA-12-14 | Txn edit | transaction_type change moves row out of expense spend | `{ "transaction_type": "income" }` | PATCH; GET /home | row no longer in `spent_so_far_minor`; sign flips to positive | P0 |
| QA-12-15 | Txn edit | Empty PATCH rejected | `{ }` | PATCH | 422 (at least one field required) | P2 |
| QA-12-16 | Txn delete | Hard delete removes row from spend | delete a counted expense | DELETE; GET /home | 204; `spent_so_far_minor` decreases by that amount; row gone from list | P0 |
| QA-12-17 | Txn delete | Re-delete idempotency | delete same id twice | DELETE x2 | first 204; second 404 `not_found` | P1 |
| QA-12-18 | Txn detail | raw_merchant_input not returned by default | GET one txn | GET /transactions/{id} | `merchant_display_name` shown; `raw_merchant_input` NOT in default response | P1 |

---

## 13. categories endpoint and client filtering

Endpoint: `GET /categories`. Schema §7 seed: 22 rows (14 consumer + 8 bank). `included_in_committed_projection` always false (omitted from payload).

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-13-01 | Categories | Returns exactly 22 seeded | fresh install | GET /categories | 22 items; all `is_system=true` | P0 |
| QA-13-02 | Categories | 14 consumer flags correct | inspect consumer rows | GET /categories | 14 `layer=consumer_spending`, `included_in_actual_spending=true`, `included_in_cash_flow=false` | P0 |
| QA-13-03 | Categories | 8 bank flags correct | inspect bank rows | GET /categories | 8 `layer=bank_movement`, `included_in_actual_spending=false`, `included_in_cash_flow=true` | P0 |
| QA-13-04 | Categories | Canonical keys present | inspect keys | GET /categories | includes `interest_bank_fee` and `cash_deposit_withdrawal` (NOT `bank_fee_interest`/`cash_movement`); all 22 keys match seed | P0 |
| QA-13-05 | Categories | included_in_committed_projection never true | inspect every row | GET /categories | field omitted from payload; per schema it is false for all 22 (projection is a template property) | P0 |
| QA-13-06 | Categories | Quick Add picker filtered to 14 consumer | client filters `layer==consumer_spending` | client render | only 14 offered; the 8 bank-movement never offered in Quick Add | P0 |
| QA-13-07 | Categories | Layer C never accepted in Quick Add (server-enforced) | `category_id=<outgoing_transfer>` in quick-add | POST quick-add | 422 `not_consumer_category`; server enforces independent of client filter | P0 |
| QA-13-08 | Categories | System categories immutable | attempt create/update/delete a category | mutate | 403 `unsupported_operation` (or no such route) | P1 |
| QA-13-09 | Categories | Hebrew labels present | inspect `label_he` | GET /categories | every row carries `label_he` placeholder | P2 |
| QA-13-10 | Categories | System categories readable by any principal | any user | GET /categories | identical 22 rows; `user_id IS NULL` rows shared read-only | P1 |

---

## 14. duplicate-looking and large-amount save-then-warn

API_CONTRACT §5/§8. Both are SAVE-THEN-WARN: row saved + non-blocking warning, never a gate.

| ID | Area | Scenario | Setup/Input | Action | Expected Result | Priority |
|---|---|---|---|---|---|---|
| QA-14-01 | Dup/Large | Near-identical recent entry → SAVED + soft warning | prior ₪33 Golda today; submit ₪33 Golda today again | POST quick-add | 201; transaction SAVED; `warnings[]` has `duplicate_looking` with `similar_transaction_id`; NOT a 4xx, NOT blocked | P0 |
| QA-14-02 | Dup/Large | Legitimate repeat (two coffees) not blocked | same as QA-14-01, user keeps it | no further call needed | both transactions persist; both count in spend | P0 |
| QA-14-03 | Dup/Large | Duplicate warning is a warning, never an error | inspect QA-14-01 | inspect response | warning lives on a 201; no `error` envelope | P0 |
| QA-14-04 | Dup/Large | Very large amount → SAVED + warning | `{ "amount": 12000, "merchant_input":"HomeCenter" }` (≥ threshold) | POST quick-add | 201; transaction SAVED (`amount_minor=-1200000`); `warnings[]` has `large_amount`; NOT blocked | P0 |
| QA-14-05 | Dup/Large | confirm_large_amount=true suppresses warning on resubmit | resubmit same large amount with `confirm_large_amount:true` | POST quick-add | 201; SAVED; no `large_amount` warning (user already confirmed) | P1 |
| QA-14-06 | Dup/Large | Large amount never a hard block | large amount, no confirm flag | POST quick-add | 201 every time; server never returns 4xx purely for size | P0 |
| QA-14-07 | Dup/Large | Undo path is explicit DELETE, not a server gate | after large/dup warning, user undoes | DELETE /transactions/{id} | 204; row removed; demonstrates save-first + explicit undo | P1 |
| QA-14-08 | Dup/Large | Duplicate detection matches amount+merchant+occurred_on within window | same amount, different merchant OR different day | POST quick-add | NO duplicate warning (not near-identical) | P2 |
| QA-14-09 | Dup/Large | Amount-only duplicates (both merchant null) detected | two ₪50 amount-only today | POST quick-add x2 | second 201 + `duplicate_looking` (both merchant null, same amount/day) | P2 |

---

## Coverage summary

| Area | # Tests | # P0 |
|---|---|---|
| 01 Quick Add save-first | 13 | 9 |
| 02 agorot / money parsing | 17 | 11 |
| 03 merchant matching / no silent merge | 14 | 9 |
| 04 aliases / 409 | 8 | 5 |
| 05 rule update-not-stack | 10 | 6 |
| 06 categorize / apply_to_existing | 8 | 5 |
| 07 recurring ZERO transactions | 10 | 6 |
| 08 Home never blends | 13 | 8 |
| 09 ownership 404 not 403 | 11 | 9 |
| 10 no PII in logs | 11 | 9 |
| 11 generic errors | 11 | 7 |
| 12 transaction list/edit/delete | 18 | 8 |
| 13 categories / filtering | 10 | 7 |
| 14 duplicate / large save-then-warn | 9 | 5 |
| TOTAL | 163 | 104 |

P0 invariant coverage confirmed: money-correctness (§2), no-silent-merge (§3, §4), recurring-zero-transactions (§7), Home-never-blends (§8), ownership-404 (§9), no-PII-in-logs (§10) each carry multiple blocking cases.

---

## Ready for code? — verdict

YES. The seven upstream docs are decision-complete, mutually consistent, and frozen; no blocking contradiction was found. This plan converts the schema's per-table test cases (DATABASE_SCHEMA §15) and the contract's per-endpoint Tests into one consolidated, pass/fail acceptance matrix of 163 cases (104 P0). Every test maps to a concrete endpoint and the schema constraint it exercises, and the seven money/double-counting/privacy/authorization invariants that define correctness for a financial tool are each pinned down as MUST-PASS before any code exists. Implementation can begin immediately; the acceptance bar is unambiguous. The only items flagged for the engineer (the QUICK_ADD save-vs-suggested-category interaction, QA-01-04/QA-13-06, and the large-amount/duplicate windows, QA-14-08/09) are clarifications already resolved by the contract, not open product decisions.

---

## Recommended FIRST coding task

Per API_CONTRACT §19 and the manual-first build filter, begin implementation with the foundation slice — NOT a feature endpoint:

1. Repo structure (FastAPI backend; Expo client skeleton can follow).
2. FastAPI skeleton (single service, `/api/v1` prefix, the standard error envelope from API_CONTRACT §5).
3. PostgreSQL connection + local/dev config (secrets externalized; pgvector extension installed but zero vectors).
4. v0.0.1 migrations for the seven active tables (`users`, `transactions`, `merchants`, `merchant_aliases`, `categories`, `category_rules`, `recurring_expense_templates`) plus empty `accounts`/`import_batches` as deferred FK targets, with every constraint/index from DATABASE_SCHEMA §3–§13 (signed agorot, `amount_minor<>0`, `occurred_on DEFAULT CURRENT_DATE`, the partial unique `(user_id, dedup_hash) WHERE dedup_hash IS NOT NULL`, `UNIQUE(user_id, normalized_merchant_name)`, `UNIQUE(user_id, normalized_alias_key)`, `UNIQUE(user_id, match_type, match_value)`, `included_in_committed_projection=false` CHECK).
5. Seed the 22 system categories (14 consumer + 8 bank-movement, canonical keys incl. `interest_bank_fee` / `cash_deposit_withdrawal`, all `is_system=true`, `user_id=NULL`, `included_in_committed_projection=false`).
6. Health endpoint (`GET /api/v1/health`) returning DB reachability, logging only the safe shape.

Acceptance for this first slice draws directly from this plan: QA-13-01..05 (exactly 22 seeded with correct flags/keys), QA-11-07 (`backend_unavailable` when DB is down, nothing saved), QA-10-06/QA-10-10 (no secrets/PII in startup or health logs), and the schema-constraint cases QA-02-04/06/07, QA-03-13, QA-04-03, QA-05-02 are exercised the moment the constraints exist.

### Exact next prompt to send to start implementation

> "Acting as the backend-api-engineer agent with the database-engineer and security-privacy-engineer agents, and using docs/DATABASE_SCHEMA_V0_0_1.md (frozen schema), docs/API_CONTRACT_V0_0_1.md (frozen contract), and docs/QA_TEST_PLAN_V0_0_1.md (the acceptance matrix) as sources of truth, implement the v0.0.1 foundation slice ONLY: (1) repo structure and a FastAPI skeleton mounted at /api/v1 with the standard error envelope; (2) a PostgreSQL connection with externalized secrets and the pgvector extension installed but unused; (3) migrations creating the seven active tables (users, transactions, merchants, merchant_aliases, categories, category_rules, recurring_expense_templates) plus empty accounts and import_batches as deferred FK targets, with EVERY constraint and index in the schema doc — signed bigint agorot with amount_minor<>0, occurred_on DEFAULT CURRENT_DATE, the partial unique (user_id, dedup_hash) WHERE dedup_hash IS NOT NULL, UNIQUE(user_id, normalized_merchant_name), UNIQUE(user_id, normalized_alias_key), UNIQUE(user_id, match_type, match_value), and the included_in_committed_projection=false CHECK; (4) a seed of the 22 system categories (14 consumer_spending + 8 bank_movement, canonical keys including interest_bank_fee and cash_deposit_withdrawal, is_system=true, user_id NULL); and (5) a GET /api/v1/health endpoint. Honor every firm invariant: signed minor units + ILS default, UTC timestamptz metadata, date-only occurred_on, user_id everywhere, raw transactions never embedded, and privacy-safe logging that emits only request id, endpoint, status, duration bucket, validation error code, confidence-level enum, and row counts — never merchant text, amount, note, or raw input. Build to satisfy QA-13-01..05, QA-11-07, and QA-10-06/QA-10-10 from the test plan. Do NOT implement any feature endpoint (quick-add, home, merchants, categorize, recurring) yet, and introduce no deferred table into the active surface. Implementation of the foundation slice only."

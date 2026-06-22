# Money App — Import Pipeline Spec (v0.0.1)

Status: Technical specification. Planning only. No code, no UI, no implementation.
Owner: backend-api-engineer (lead), synthesizing database-engineer, qa-tester, security-privacy-engineer, and product-architect perspectives.
Inputs (approved): docs/PRD_V0_1.md, docs/MVP_EXECUTION_ALIGNMENT.md, docs/IMPORT_SPEC_BANK_STATEMENT_HEBREW_V1.md, docs/SANITIZED_BANK_STATEMENT_SAMPLE.csv
Stack (firm): FastAPI single backend, PostgreSQL + pgvector, REST/JSON, pandas/openpyxl for parsing, integer minor units, UTC timestamps, raw transactions in SQL only (never embedded).
Date: 2026-06-13

Correction to prior docs: MVP_EXECUTION_ALIGNMENT.md states the sample fixtures do not exist. That claim is now OUTDATED. Both docs/IMPORT_SPEC_BANK_STATEMENT_HEBREW_V1.md and docs/SANITIZED_BANK_STATEMENT_SAMPLE.csv exist and have been read. The import parser may now be implemented and tested against the sanitized sample.

---

## 1. Purpose

The v0.0.1 importer ingests one concrete, known file shape — an Israeli bank current/checking-account export — turns its rows into normalized, signed, integer-minor-unit transactions, deduplicates them deterministically, assigns coarse bank-statement categories, and presents a preview before commit. It exists to prove the foundational loop: import to normalize to persist to categorize to overview. Every layer above (totals, summaries, insights, AI) inherits the correctness of this stage, so correctness, determinism, and privacy are prioritized over breadth.

The v0.0.1 importer SUPPORTS:
- A single supported file profile: `bank_statement_hebrew_v1` (defined in section 2), supplied as `.xlsx` (one sheet) or as the structurally identical sanitized `.csv`.
- Dynamic header detection by Hebrew column names (never a fixed row index).
- Skipping of metadata, title, summary, and blank rows.
- Parsing of `DD/MM/YYYY` dates into date-only `posted_date` and `value_date`.
- Parsing of credit (`זכות`) and debit (`חובה`) into a single signed `amount_minor` plus an explicit `direction`.
- File-profile-level placeholder detection for the unused-side `15` placeholder (section 8).
- Deterministic deduplication and safe re-import (section 12).
- Coarse, bank-statement-level category inference (section 13) with a credit-card-settlement flag to prevent later double-counting (section 14).
- A privacy-safe import preview and structured, PII-free logging.

The v0.0.1 importer INTENTIONALLY DOES NOT SUPPORT:
- Itemized credit-card / consumer-merchant exports (a separate profile, later milestone).
- Generic "any CSV" import or arbitrary user-defined column mapping UI. v0.0.1 targets one known shape; a general mapping wizard is deferred.
- Multi-currency conversion. Currency is stored (`ILS` default) but not converted.
- Multi-sheet workbooks, pivot tables, or merged-cell layouts beyond the single-sheet `A1:I~60` shape.
- Recurring detection, unusual detection, MonthlySummary, AI, RAG, or any embedding (per MVP_EXECUTION_ALIGNMENT.md). No row from this pipeline is ever embedded.
- Automatic bank/API sync, Apple Pay/Wallet, or open banking.
- Auto-commit. A human reviews the preview before persistence in v0.0.1.

---

## 2. Supported file profile: `bank_statement_hebrew_v1`

Definition. `bank_statement_hebrew_v1` is an Israeli bank current/checking-account movement export, originally `.xlsx`, one sheet, used range approximately `A1:I60`. Layout: a leading blank/title area, four metadata rows (report title; account + export timestamp; account type; date range), then a Hebrew table header, then transaction rows. The sanitized CSV fixture has the same column structure; because the leading blank row collapses differently in CSV, in the fixture the header is on line 5 and data starts on line 6. This is exactly why the header MUST be detected dynamically (section 3) and never by a fixed row index.

Profile detection algorithm (all soft signals; the header match in section 3 is the decisive one):
1. Open the file (xlsx via openpyxl/pandas, or csv). Read the first ~15 rows as raw strings without assuming a header.
2. Scan rows for a row containing a strong subset of the canonical Hebrew headers (`יתרה`, `תאריך ערך`, `זכות`, `חובה`, `תיאור`, `אסמכתא`, `סוג פעולה`, `תאריך`). A match of the required headers (`תאריך ערך`, `זכות`, `חובה`, `תיאור`, `תאריך`) plus at least one of (`אסמכתא`, `סוג פעולה`, `יתרה`) confirms the profile.
3. Confirm the column ordering is consistent with the A-I mapping in section 5 (B=balance ... I=posted date). Order is a confirming signal, not a hard requirement, because matching is by header name.
4. If the header row is found and required headers are present, classify as `bank_statement_hebrew_v1`. Otherwise return `unsupported_file_profile` (section 16). v0.0.1 has exactly one profile; "unknown" is a hard, friendly error, not a fallback mapping wizard.

Why this is a bank/checking statement and not consumer-spending detail:
- The export records account movements (balance after each row in `יתרה`), value date vs posted date, a bank reference (`אסמכתא`), and a bank operation code (`סוג פעולה`). These are account-ledger artifacts, not point-of-sale fields.
- A credit-card line in this file is a single monthly settlement ("חיוב כרטיס אשראי") — one aggregate payment to the card issuer — NOT the individual restaurant/store purchases. The true merchants live only in a separate itemized card export.
- Therefore categories here are coarse cash-flow categories (section 13), and any card-settlement line is flagged (section 14) so that when itemized card files arrive later, spending is not double-counted.

How it differs from an itemized credit-card export (a future, separate profile): a card export has one signed amount column (or a single charge column), real merchant names per row, no running account balance, no value-date/posted-date split, and card-specific fields (e.g., card last-4, installment markers). v0.0.1 does not parse that shape.

---

## 3. Header detection

The real transaction header is detected dynamically by Hebrew column names, never by row index.

Canonical headers and their normalized internal field (section 5 has full mapping):
- `יתרה` -> balance_after
- `תאריך ערך` -> value_date
- `זכות` -> credit_amount
- `חובה` -> debit_amount
- `תיאור` -> raw_description
- `אסמכתא` -> reference
- `סוג פעולה` -> operation_type
- `תאריך` -> posted_date

Header-cell normalization before matching (critical — the sample's `תיאור` header carries long trailing space padding, e.g. `"תיאור                                            "`):
1. Strip leading/trailing whitespace (including the trailing padding).
2. Collapse internal runs of whitespace to a single space.
3. Strip Unicode invisible/zero-width and bidi control characters (e.g. U+200B, U+200E, U+200F, U+202A-U+202E, U+FEFF).
4. Apply Unicode NFC normalization so Hebrew composes consistently.
5. Compare against the canonical set after the same normalization is applied to both sides. Matching is exact-after-normalization (not substring), to avoid a stray cell that merely contains a header word being mistaken for the header.

Header-row search algorithm:
1. Iterate rows from the top (cap the scan at the first 20 rows; a header beyond that signals an unexpected structure -> `no_header_row_found`).
2. For each row, normalize every cell and count how many normalized cells exactly match a canonical header.
3. Select the first row where all REQUIRED headers (`תאריך ערך`, `זכות`, `חובה`, `תיאור`, `תאריך`) are present. Record the column index of each matched header by NAME; build the column-index map from this row. Never assume column letters from a remembered guess — always bind to the detected header positions.
4. Record `header_row_index`. Data parsing starts at `header_row_index + 1` and continues until a terminating condition (blank row at/after data, an account-summary row, or end of used range — see section 4).
5. If no row satisfies the required set within the scan window, return `no_header_row_found` (section 16). If the row is found but one or more required headers are missing, return `missing_required_columns` listing which (by canonical Hebrew name).

Tolerance notes: leading empty column A is expected and ignored. Extra unrecognized columns are ignored (not an error) as long as required headers are present. Header matching is whitespace- and invisible-char-tolerant by construction (step normalization above), which directly handles the padded `תיאור` header in the sample.

---

## 4. Metadata handling

Rows that are NOT transactions must be detected and skipped: the title row, the account+export-timestamp row, the account-type row, the date-range row, any account-summary/footer row, and any blank row. Detection is positional-agnostic and rule-based, not "skip the first N rows."

Skip rules:
- Any row ABOVE the detected `header_row_index` is metadata/title -> skip from transaction parsing.
- A row is BLANK if, after trimming, all mapped cells are empty -> skip (do not terminate on a single blank line inside the scan window, but a blank row after data has begun is treated as end-of-table; see below).
- A row is a NON-TRANSACTION row if it lacks a parseable required field set: specifically, if `posted_date` (`תאריך`) does not parse as `DD/MM/YYYY` AND `value_date` (`תאריך ערך`) does not parse, the row is not a transaction (it is a summary/footer/label row) -> skip and count under `skipped_non_transaction_rows`, do not treat as an error.
- An account-summary row (e.g. an opening/closing balance line or a totals line) typically has no valid date pair and/or no credit/debit pair -> skipped by the same date-pair rule above.
- End-of-table: once data rows have started, the first all-blank row OR the end of the used range terminates parsing.

Metadata that MAY be stored safely (sanitized, non-identifying):
- Detected statement date range (from the `מתאריך ... עד תאריך ...` row), parsed into two date-only values, stored on the ImportBatch as `detected_period_start` / `detected_period_end`. These are coarse dates, not identity.
- A sanitized account-type LABEL (e.g. a coarse enum like `checking`), derived from the account-type row by mapping to a controlled vocabulary — NEVER the raw masked string verbatim, and never any number.
- File profile name (`bank_statement_hebrew_v1`) and row counts.

Metadata that MUST NOT be stored or logged:
- Account number / masked account identifier (the `חשבון:...` value).
- The export timestamp tied to the account row if it could aid re-identification (the coarse date range is sufficient and is stored instead).
- Any raw metadata cell verbatim, original filename containing PII, or full row text.

---

## 5. Column mapping

Each detected Hebrew column binds to a normalized internal field by header name (positions come from section 3 detection, shown here as the typical Excel A-I layout for reference only).

| Excel col (typical) | Hebrew header | Internal field | Required | Type / notes |
|---|---|---|---|---|
| A | (empty) | (ignored) | no | Leading empty column. Always ignored. |
| B | יתרה | balance_after_minor | no | Running balance after the row. May be blank. Parsed to signed minor units (section 9). Not required; never reject a row for missing balance. |
| C | תאריך ערך | value_date | yes | `DD/MM/YYYY`, stored date-only. |
| D | זכות | credit_amount (raw) | conditional | Incoming/credit amount. Required as part of the credit/debit pair, subject to placeholder logic (section 8). |
| E | חובה | debit_amount (raw) | conditional | Outgoing/debit amount. Required as part of the credit/debit pair, subject to placeholder logic (section 8). |
| F | תיאור | raw_description | yes | Raw counterparty/operation text. Preserved verbatim (section 10). Header has trailing padding (section 3). |
| G | אסמכתא | reference | recommended | Bank reference; used in dedup (section 12). May be blank; absence weakens but does not break dedup. |
| H | סוג פעולה | operation_type | recommended | Bank operation code (e.g. 222/162/272). Soft categorization signal (section 11) and dedup field. |
| I | תאריך | posted_date | yes | `DD/MM/YYYY`, stored date-only. Primary transaction date. |

Required-to-accept-a-row set: a parseable `posted_date` (`תאריך`), a parseable `value_date` (`תאריך ערך`), a resolvable signed amount from the credit/debit pair (section 7/8), and a `raw_description` (`תיאור`). `יתרה`, `אסמכתא`, `סוג פעולה` are recommended, not required. Missing any REQUIRED HEADER (not value) is a structural error (`missing_required_columns`); a missing required VALUE in an otherwise-transaction row routes that row to invalid/ambiguous handling per sections 6-8, not to a whole-file failure.

---

## 6. Date parsing

- `posted_date` is parsed from `תאריך` (Excel col I); `value_date` from `תאריך ערך` (Excel col C). Both use format `DD/MM/YYYY`.
- Storage is DATE-ONLY (no time component) for both. Israeli bank statements are day-granular; do not fabricate a time.
- UTC is used ONLY for metadata timestamps (`imported_at`, `created_at`, `updated_at`), never for the financial dates themselves. The financial dates are calendar dates and are stored as such.
- `posted_date` is the primary date for ordering, monthly bucketing, and totals. `value_date` is stored separately and used in the dedup hash.

Format and ambiguity handling:
- The profile fixes the format as `DD/MM/YYYY`. The parser must NOT auto-detect MM/DD; it parses day-first deterministically for this profile.
- A value where day > 12 confirms day-first and is parsed normally. A value where both day and month are <= 12 is still parsed day-first (profile-fixed); no per-row guessing.
- xlsx caveat: Excel may store dates as serial numbers or native date cells rather than `DD/MM/YYYY` strings. The parser must handle both: if the cell is a native date/serial, read its calendar date directly; if it is a string, parse `DD/MM/YYYY`. Both resolve to the same date-only value.

Invalid / missing dates:
- If `posted_date` does NOT parse but `value_date` does (or vice versa) in an otherwise-transaction-looking row, the row is `invalid_date` -> excluded from import, surfaced in preview under invalid rows with a privacy-safe reason. Do not silently coerce.
- If NEITHER date parses, the row is not a transaction (metadata/summary) and is skipped per section 4, not counted as an error.
- A date outside the detected statement period is allowed (banks sometimes include a boundary row) but raises a non-blocking preview warning.

---

## 7. Amount parsing

Goal: produce one signed integer `amount_minor` (agorot) plus an explicit `direction` ('credit' | 'debit') from the `זכות` (credit) / `חובה` (debit) pair.

Sign convention (firm):
- `זכות` (credit / incoming) -> positive `amount_minor`, `direction = 'credit'`.
- `חובה` (debit / outgoing) -> negative `amount_minor`, `direction = 'debit'`.
- Examples: credit `500.00` -> `amount_minor = +50000`, `direction='credit'`; debit `149.00` -> `amount_minor = -14900`, `direction='debit'`.

Numeric normalization of a raw amount cell:
1. If a native numeric cell (xlsx), use the numeric value directly.
2. If a string: strip whitespace and invisible chars; remove a currency symbol if present (`₪`); interpret `,` as a thousands separator and `.` as the decimal separator (Israeli `he-IL` convention for this profile); handle parentheses as negative if ever present (not expected in this profile).
3. Convert to minor units by rounding the major-unit decimal to exactly 2 fractional digits then multiplying by 100 to an integer. Use decimal arithmetic (never binary float) to avoid rounding drift. Reject if more than 2 fractional digits remain after normalization (-> `invalid_amount`).

Resolving the credit/debit pair (works with the placeholder detector in section 8):
- Determine, per row, which sides are "real amounts" vs the profile placeholder (section 8). Let R = the set of sides whose value is a real, non-placeholder amount.
- Exactly one real side (the normal case): that side determines amount and direction. Credit-only -> positive/credit. Debit-only -> negative/debit.
- BOTH sides real (R = {credit, debit}, neither is the placeholder): AMBIGUOUS. Do not guess. Route to ambiguous-review; excluded from auto-import; surfaced in preview ambiguous count with a privacy-safe reason. (Optional disambiguation by balance delta in section 9 may be offered for manual confirmation but is never auto-applied silently.)
- NEITHER side populated/real (both empty or both placeholder): the row carries no movement. If it also lacks valid dates it is a non-transaction (skip, section 4); if it has valid dates but no resolvable amount it is `invalid_amount` (excluded, surfaced).
- Zero amount on the single real side: treated as `invalid_amount` for a movement row (a zero-value movement is not a meaningful transaction in v0.0.1) and surfaced; not silently imported.

`balance_after_minor` is parsed by the same numeric normalization (section 9) but is signed by its own value (a balance can be negative) and is independent of `direction`.

---

## 8. Special placeholder behavior (the `15` placeholder)

In this export the UNUSED side of the credit/debit pair contains the literal `15` (not blank). A credit row has `זכות`=real, `חובה`=`15`; a debit row has `חובה`=real, `זכות`=`15`. The number `15` MUST NOT be hardcoded as "empty" forever — it is a property of this file/profile, not a universal rule. The pipeline implements a profile-level placeholder detector run once per file, before per-row amount resolution.

Placeholder-candidate detection (per file, deterministic):
1. Read all parsed credit and debit raw values across the data rows.
2. For each row, identify rows where exactly one side has a value and the other side repeats a constant candidate value. Tally candidate constants that appear on the "other" side.
3. A candidate C qualifies as the empty-side placeholder if: in NEARLY EVERY row where one side holds a non-candidate amount, the other side equals C. Operationalize "nearly every" as a high threshold (e.g. >= 90% of qualifying rows, with a minimum sample so a 1-2 row file does not over-trust). The candidate must appear on BOTH sides across the file (i.e. it is the filler on whichever side is unused), consistent with `15` appearing in debit on credit rows and in credit on debit rows.
4. If a qualifying placeholder C is found, record it on the ImportBatch as the profile placeholder for THIS import (e.g. `detected_placeholder = "15"`). Per-row, a side equal to C is treated as EMPTY/unused.
5. If no candidate qualifies, no placeholder is assumed; the parser falls back to "real value on exactly one side, the other side blank" and treats any genuinely populated both-sides row as ambiguous (section 7).

Fallback / manual-review rules:
- Both sides real (neither equals the detected placeholder): AMBIGUOUS -> manual review (section 7). Never auto-resolve.
- The real transaction amount genuinely equals the placeholder value (e.g. a true `15.00` payment in a file whose placeholder is `15`): this row is AMBIGUOUS because the real side cannot be distinguished from the filler side by value alone. Resolve via, in order: (a) balance-delta check (section 9) if `יתרה` is present and consistent — the side whose sign matches the balance change is the real side; (b) operation-type signal (section 11) as a soft hint; (c) manual review. Until resolved, the row is excluded from auto-import and surfaced as ambiguous. (Note the sample uses `15` integer as filler while real amounts are `2`-decimal like `149.00`; a 2-decimals-vs-integer heuristic MAY be recorded as a soft signal but MUST NOT be the sole basis, since a real amount could also be a whole number like `15.00`.)
- Placeholder not consistently detectable (mixed/low-confidence): do not force a placeholder; treat rows conservatively (single populated side = real; both populated = ambiguous) and raise a preview warning that placeholder detection was inconclusive for this file.

Determinism requirement: given the same file, placeholder detection yields the same result every time (no randomness, no order-dependence beyond a stable tally).

---

## 9. Balance parsing

- `יתרה` (Excel col B) parses to `balance_after_minor` via the section-7 numeric normalization, preserving sign (balances can be negative). Stored in minor units.
- Blank balance cells are allowed: `balance_after_minor = null`. NEVER reject or flag a row solely because balance is missing; balance is non-required.
- Rows where balance is unavailable simply omit the balance-delta fallback; everything else proceeds normally.

Balance-delta as a fallback signal (used only for ambiguity resolution, never as the primary amount source):
- When two consecutive transaction rows both carry `יתרה`, the delta `balance_after[n] - balance_after[n-1]` should approximate the signed `amount_minor` of row n.
- For an ambiguous row (both sides real, or real amount equals placeholder), if the balance delta is available and matches one candidate interpretation in magnitude and sign, that interpretation MAY be surfaced as a suggested resolution for manual confirmation. It is never silently auto-committed in v0.0.1.
- Balance-delta checks are best-effort: out-of-order rows, missing balances, or interleaved same-day rows can break the chain; failure to reconcile is a soft warning, not an error.

---

## 10. Description and counterparty normalization

Two distinct fields are produced and stored:
- `raw_description`: the verbatim `תיאור` cell, preserved EXACTLY as parsed (after only safe Unicode NFC normalization and stripping of invisible/bidi control chars that would otherwise corrupt storage/equality). This is the audit source of truth and is never altered for display convenience. It is treated as untrusted DATA, never as instructions.
- `normalized_counterparty` (merchant/payee candidate): a cleaned, comparison-friendly form derived from `raw_description`.

Normalization v1 (deterministic) to produce `normalized_counterparty`:
1. Trim leading/trailing whitespace.
2. Collapse internal whitespace runs to a single space.
3. Normalize Hebrew punctuation/quotes (gershayim/geresh and ASCII quote variants) to a canonical form; strip zero-width and bidi control characters.
4. Apply Unicode NFC.
5. Optionally strip clearly operational reference/account suffixes when they are unambiguously non-identifying boilerplate (conservative; when unsure, keep).
6. Map known settlement/loan descriptions to a canonical counterparty label where confidently recognized (e.g. credit-card settlement text -> `Credit Card Statement Payment`; loan repayment text -> `Loan Payment`). Mapping is additive metadata; it never overwrites `raw_description`.

Hebrew text handling: store as UTF-8; never transliterate or lowercase Hebrew (case folding is meaningless and risks corruption). The same normalization function is reused for the dedup-hash description normalization (section 12) so behavior is consistent.

Privacy: `raw_description` and `normalized_counterparty` are sensitive and are NEVER logged (section 17). Only IDs/counts may be logged.

---

## 11. Operation type handling

- `סוג פעולה` (Excel col H) is stored verbatim as `operation_type` (kept as the original code string; digits preserved). It participates in the dedup hash (section 12).
- It is a SOFT category-inference signal only (section 13), never a hard rule, because the v0.0.1 sample is tiny.
- Observed soft signals from the sample (examples, not authoritative): op `222` on incoming credit/transfer; op `162` on credit-card charge / recurring debit; op `272` on outgoing transfer. These bias initial inference but are always overridable by description signals and by user correction, and never on their own assign a final category with high confidence.
- Confidence: when operation_type is the only signal, inference confidence stays low and the row leans toward `Other bank movement` rather than a specific category unless the description agrees.

---

## 12. Deduplication

`dedup_hash` is a deterministic hash over the following NORMALIZED fields (never the row number):
- user_id
- account_id
- posted_date (date-only, ISO `YYYY-MM-DD`)
- value_date (date-only, ISO `YYYY-MM-DD`)
- amount_minor (signed integer)
- direction ('credit' | 'debit')
- normalized raw_description (the section-10 normalization: trim + collapse spaces + normalize Hebrew punctuation + strip invisible/bidi chars + NFC)
- reference (`אסמכתא`, trimmed; empty string if absent)
- operation_type (`סוג פעולה`, trimmed; empty string if absent)

Hashing rules:
- Build a canonical string by joining the fields above in a FIXED order with a non-colliding separator, after applying the documented normalization to each. Hash with a stable algorithm (e.g. SHA-256) and store the hex digest as `dedup_hash`.
- Normalization is applied BEFORE hashing so that cosmetic whitespace/punctuation/invisible-char differences in re-exports do not produce a different hash.
- Uniqueness is enforced at the database level as `unique(user_id, dedup_hash)` (per DATABASE_SCHEMA_V0_0_1.md), so dedup is authoritative in storage, not just in app logic.

Re-import behavior:
- Importing the SAME file twice does not double-count: each incoming row's `dedup_hash` is checked against existing transactions for that user; matches are counted as `duplicate_count` and skipped (not inserted).
- Near-duplicates (same amount/date but different reference or operation_type) hash differently and are NOT auto-merged; they are imported as distinct and surfaced in preview counts so the human can notice. v0.0.1 does not do fuzzy dedup — only deterministic exact-hash dedup — to avoid silently dropping legitimate same-amount transactions.
- Idempotency: re-running an identical import is safe and converges to the same persisted set (no duplicates created).

---

## 13. Category inference v1 for bank statements

These are coarse, bank-statement-level categories (NOT consumer-spend categories). All inference is heuristic; when signals conflict or are weak, default to `Other bank movement` and leave a low confidence score. A confidence score is stored per categorization (manual user corrections are always authoritative over inference).

Categories and their likely signals (description text + operation_type, both soft):
1. Income — incoming `direction=credit`; description suggests salary/payroll/benefit; op like `222` (incoming). Default for clearly incoming non-transfer credits.
2. Incoming transfer — `direction=credit`; description like `העברה נכנסת` (incoming transfer); op `222`.
3. Outgoing transfer — `direction=debit`; description like `העברה יוצאת` (outgoing transfer); op `272`.
4. Credit card payment / settlement — `direction=debit`; description like `חיוב כרטיס אשראי` (card charge) or known issuer settlement text; op `162`. ALSO sets the settlement flag (section 14).
5. Loan payment — `direction=debit`; description indicating loan/mortgage repayment (`הלוואה`/`משכנתא`).
6. Interest / bank fee — small `direction=debit` (or occasional credit) with fee/interest/commission description (`עמלה`/`ריבית`).
7. Cash deposit / withdrawal — description/op indicating ATM/cash (`מזומן`/`כספומט`); direction sets deposit vs withdrawal.
8. Other bank movement — DEFAULT when nothing confidently matches. Uncategorized-but-classified-as-Other is acceptable and surfaced; never force a specific category on weak evidence.

Explicit rule: inference is best-effort and low-stakes. A row whose category is uncertain stays `Other bank movement` (or null/uncategorized per schema) and appears in the preview's uncategorized/low-confidence count rather than being mis-bucketed. The sample's op codes (`222`/`162`/`272`) are examples that bias inference, not authoritative rules.

---

## 14. Double-counting prevention

A bank-level credit-card payment is a SETTLEMENT (one aggregate transfer to the card issuer), not consumer spending. If it were counted as normal spending AND the itemized card export (with each restaurant/store purchase) were imported later, the same money would be counted twice.

Mechanism:
- Any row inferred as `Credit card payment / settlement` (section 13) sets a boolean flag `is_card_settlement = true` (and/or a settlement marker such as `transfer_or_card_settlement`) on the transaction.
- Settlement-flagged transactions are EXCLUDED from consumer-spending totals and category-spend rankings. They remain visible as cash-flow movements (so the account balance and cash-flow view stay correct) but do not inflate "spent on categories."
- This makes the later arrival of itemized card files safe by construction: when those files are imported (a future profile), their itemized purchases become the spending of record, and the corresponding bank-level settlement is already excluded — no double count.
- The flag is set at import time but is correctable: a user can override the classification, and corrections are authoritative.

---

## 15. Import preview

The preview is shown BEFORE commit and contains (sensitive values masked; see below):
- Detected file profile (`bank_statement_hebrew_v1`).
- Detected statement date range (`detected_period_start` / `detected_period_end`).
- Total rows parsed.
- Valid rows (parse + amount resolved successfully).
- Imported count (valid, non-duplicate rows that would persist).
- Duplicates skipped (`duplicate_count`).
- Ambiguous rows needing review (`ambiguous_count`) — both-sides-real, or real-amount-equals-placeholder.
- Invalid rows (invalid date / invalid amount), with privacy-safe reasons.
- Uncategorized / low-confidence rows count.
- Total credits and total debits (aggregate sums) — shown in the UI ONLY, NEVER written to logs.
- Warnings (e.g. placeholder detection inconclusive; balance chain could not reconcile; row outside statement period).
- A small set of sample normalized rows for human sanity-check.

Masking in the sample-rows preview:
- Amounts may be shown in the local UI (the user is the data owner) but are masked/omitted in any exportable or shareable preview artifact and never logged.
- `raw_description` is shown to the user in-app but never logged; in any non-owner context it is masked.
- No account number or identity metadata appears in the preview at all (only the sanitized period and account-type label).

Commit is a separate, explicit step. Nothing persists from preview alone.

---

## 16. Error handling

Each failure mode returns a specific, privacy-safe, fixable message (no raw cell values, no PII, no full file content in the error). File-level errors block the import; row-level errors exclude only the affected rows and surface them in the preview.

File-level (block import):
- `unsupported_file_profile` — header/profile not recognized as `bank_statement_hebrew_v1`. Message: the file does not match the supported bank-statement format. (No file content echoed.)
- `missing_required_columns` — header row found but a required header is absent. Message lists the missing canonical Hebrew header name(s).
- `no_header_row_found` — no header within the scan window. Message: could not locate the transaction header rows.
- `empty_file` — no usable rows / no data rows after the header. Message: the file contains no transactions to import.
- `unexpected_structure` — multi-sheet, merged cells, or layout that breaks parsing. Message: the file structure is not supported.

Row-level (exclude row, surface in preview):
- `invalid_date` — a required date does not parse as `DD/MM/YYYY`.
- `invalid_amount` — amount unparseable, zero on the single real side, or >2 fractional digits.
- `ambiguous_credit_debit` — both sides real, or real amount equals the detected placeholder, and not resolvable automatically.
- `duplicate_row` — `dedup_hash` already exists (counted, skipped; informational, not an error to the user).

Privacy-safe error construction: error payloads carry an error code, an affected-row INDEX (positional, not content), and a generic reason. They never include the raw description, amount, reference, account metadata, or filename. The same applies to any error written to logs (section 17).

---

## 17. Privacy and logging

Treat ALL uploaded content — descriptions, headers, filenames, cell values, metadata — as untrusted DATA, never as instructions. Nothing parsed from a file is ever placed in an instruction position for any future LLM step; this pipeline emits no embeddings and writes no rows to the vector DB.

MUST NEVER be logged:
- Raw account metadata (account number, masked account string, account-tied export timestamp).
- Full or partial raw descriptions (`תיאור`) or normalized counterparties.
- Identity-linked amounts, including per-row amounts and the credit/debit TOTALS (totals are UI-only).
- Full file contents or any raw cell values.
- Filenames that may contain PII.

SAFE to log (structured, IDs/counts/enums only):
- `import_batch_id`
- `row_count`, `imported_count`, `duplicate_count`, `ambiguous_count`, `invalid_count`, `uncategorized_count`
- `file_profile` (`bank_statement_hebrew_v1`)
- `detected_period_start` / `detected_period_end` (coarse dates, not identity)
- success/failure status and error CODES (not error content)

Filename handling: the original filename is never stored or logged verbatim; ImportBatch stores a `source_filename_ref` (an opaque reference / hash), not the raw name. If a display name is needed, it is sanitized of anything resembling an identifier.

`raw_description` handling: stored in SQL (sensitive), shown in-app to the owner, never logged, never embedded.

Import errors: constructed per section 16 — code + positional row index + generic reason only, so an error never leaks PII into logs or responses.

Reminder (firm): raw transactions live in SQL ONLY and are never embedded. The import pipeline creates no Embedding rows.

---

## 18. Test cases

Built on the sanitized sample (REF001-REF005) plus synthesized edge fixtures. Each gives the input condition and the expected normalized result/behavior.

1. Normal credit row (REF001) — Input: value 01/01/2026, credit 500.00, debit 15 (placeholder), desc "זיכוי נכנס לדוגמה", ref REF001, op 222, date 01/01/2026. Expected: `amount_minor=+50000`, `direction='credit'`, `posted_date=2026-01-01`, `value_date=2026-01-01`, debit side recognized as placeholder, category leans Income/Incoming transfer, imported.

2. Normal debit row (REF004) — Input: 04/01/2026, credit 15 (placeholder), debit 260.00, desc "העברה יוצאת לדוגמה", ref REF004, op 272. Expected: `amount_minor=-26000`, `direction='debit'`, category `Outgoing transfer`, imported.

3. Placeholder / unused-side behavior (the `15`) — Input: the five sample rows. Expected: profile placeholder detector identifies `15` as the empty-side placeholder (appears on the unused side in nearly every row), records `detected_placeholder="15"`; every `15` side is treated as empty; each row resolves to exactly one real side.

4. Real small amount edge case (genuine 15.00) — Input: a row with credit `15.00` (two decimals, real) and debit `15` (filler) in a file whose placeholder is `15`. Expected: row flagged `ambiguous_credit_debit` (real value collides with placeholder value); resolution attempted via balance delta / op-type as suggestion; excluded from auto-import; surfaced in `ambiguous_count`. Never silently imported as either side.

5. Blank balance — Input: a transaction row identical to REF002 but with `יתרה` empty. Expected: `balance_after_minor=null`, row still imported normally; no error, no flag; balance-delta fallback simply unavailable for adjacent ambiguity.

6. Duplicate re-import — Input: import the full sample, then import the identical file again. Expected: first import persists 5; second import yields `duplicate_count=5`, `imported_count=0`, no new rows; `unique(user_id, dedup_hash)` holds; totals unchanged.

7. Invalid date — Input: a row with `תאריך`="32/13/2026" but otherwise valid. Expected: `invalid_date`, row excluded, surfaced in preview invalid rows with code-only reason; rest of file imports.

8. Missing required column — Input: a file whose header lacks `חובה`. Expected: file-level `missing_required_columns` naming `חובה`; nothing imported.

9. Credit-card settlement row (REF002) — Input: 02/01/2026, credit 15 (placeholder), debit 149.00, desc "חיוב כרטיס אשראי לדוגמה", ref REF002, op 162. Expected: `amount_minor=-14900`, `direction='debit'`, category `Credit card payment / settlement`, `is_card_settlement=true`, EXCLUDED from consumer-spending totals (section 14), still counted in cash flow.

10. Loan payment row — Input: synthesized debit row, desc indicating "הלוואה" repayment, op debit-like. Expected: `direction='debit'`, category `Loan payment` (heuristic), imported; not a card settlement.

11. Incoming transfer row (REF003) — Input: 03/01/2026, credit 3000.00, debit 15 (placeholder), desc "העברה נכנסת לדוגמה", ref REF003, op 222. Expected: `amount_minor=+300000`, `direction='credit'`, category `Incoming transfer`, imported.

12. Outgoing transfer row (REF004) — covered in test 2; explicit expectation: category `Outgoing transfer`, `amount_minor=-26000`, `direction='debit'`.

13. Both credit and debit populated (ambiguous) — Input: a row with credit 200.00 AND debit 80.00 (neither equals placeholder). Expected: `ambiguous_credit_debit`, excluded from auto-import, surfaced in `ambiguous_count`; balance-delta may be offered as a manual-resolution suggestion but is not auto-applied.

14. Neither credit nor debit populated — Input: a row where both sides are blank or both equal the placeholder. Expected: if dates also fail to parse -> skipped as non-transaction (section 4); if dates are valid but no resolvable amount -> `invalid_amount`, excluded, surfaced. No movement imported.

15. Privacy / logging test — Input: import the sample with logging enabled. Expected: emitted logs contain ONLY `import_batch_id`, counts, `file_profile`, coarse period dates, status, and error codes. Assert NO `raw_description` text, NO amounts (including credit/debit totals), NO reference values, NO account metadata, NO raw filename appear in any log line. Error logs carry codes + positional row index only.

Additional structural tests: empty file -> `empty_file`; header with padded `תיאור` -> header detection still matches (whitespace/invisible-char tolerant); header on a different line than the xlsx (the CSV fixture's line-5 header) -> dynamic detection finds it regardless of index; re-export with cosmetic whitespace differences -> same `dedup_hash`, recognized as duplicate.

---

## 19. Acceptance criteria

The v0.0.1 import pipeline spec is complete and ready for implementation when ALL of the following hold:
1. `bank_statement_hebrew_v1` is defined with a deterministic profile-detection method and a clear distinction from itemized card exports (section 2).
2. Header detection is specified by Hebrew column names with whitespace/invisible-char tolerance (including the padded `תיאור` header) and a bounded scan, never a fixed row index (section 3).
3. Metadata/blank/summary/non-transaction row skipping is rule-based and positional-agnostic, with explicit lists of storable vs forbidden metadata (section 4).
4. Every required and optional column is mapped to a normalized internal field with required/optional status (section 5).
5. Date parsing fixes `DD/MM/YYYY`, stores date-only, reserves UTC for metadata, and defines invalid/missing/xlsx-serial handling (section 6).
6. Amount parsing yields a single signed `amount_minor` plus explicit `direction`, with separator/decimal rules and defined behavior for one-real-side, both-real, and neither-populated cases (section 7).
7. The `15` placeholder is handled by a per-file detector (not hardcoded) with the "nearly every row" test and manual-review fallbacks for both-real, real==placeholder, and inconclusive cases (section 8).
8. Balance parsing handles blanks and defines the balance-delta fallback as suggestion-only (section 9).
9. Description normalization preserves `raw_description` verbatim and produces a `normalized_counterparty`, with Hebrew-safe rules and a no-log guarantee (section 10).
10. Operation type is stored and used only as a soft signal (section 11).
11. Deduplication is deterministic over the listed normalized fields (never row number), enforced by a DB unique constraint, with defined re-import and near-duplicate behavior (section 12).
12. Bank-statement category inference v1 is defined as heuristic with `Other bank movement` as the safe default (section 13).
13. Double-counting prevention via a card-settlement flag and spend-total exclusion is specified (section 14).
14. Import preview content and masking rules are defined, with credit/debit totals UI-only (section 15).
15. Every error state has a specific, privacy-safe, fixable message at the correct file/row scope (section 16).
16. Privacy/logging rules enumerate forbidden vs safe logs, filename-ref handling, and the no-embedding reminder (section 17).
17. Test cases cover all listed conditions with concrete expected results, including the no-PII-in-logs assertion (section 18).
18. The spec is consistent with firm decisions: FastAPI single backend, Postgres + pgvector, integer minor units, UTC for metadata only, raw transactions in SQL and never embedded, deterministic handling, untrusted-input treatment of all file content. No code is included.

Not in scope of "spec complete": the parser implementation itself (built next, against the now-available sanitized sample), and entities/constraints owned by DATABASE_SCHEMA_V0_0_1.md.

---

## 20. Next recommended prompt

Recommendation: proceed to docs/CATEGORY_TAXONOMY.md next (not DATABASE_SCHEMA_V0_0_1.md yet).

Justification: the build-filter document sequence (MVP_EXECUTION_ALIGNMENT.md section 8) is CATEGORY_TAXONOMY -> MERCHANT_NORMALIZATION_SPEC -> DATABASE_SCHEMA_V0_0_1 -> API_CONTRACT_V0_0_1 -> WIREFRAMES -> QA_TEST_PLAN. This import spec already commits to a concrete set of coarse bank-statement categories (section 13) and a card-settlement exclusion flag (section 14); those need to be reconciled with, and folded into, the canonical default taxonomy before the schema hardcodes category seed data and before merchant normalization maps descriptions to categories. Writing the schema first would risk baking in categories that the taxonomy later revises, forcing a migration. The taxonomy is also a prerequisite for MERCHANT_NORMALIZATION_SPEC (which maps payees to categories) and feeds both the schema's category seed and the API contract. So the correct order is taxonomy first, then merchant normalization, then schema.

Exact next prompt to send after approving this spec:

> "Acting as the fintech-researcher agent with the product-architect agent, and using docs/PRD_V0_1.md as the product vision, docs/MVP_EXECUTION_ALIGNMENT.md as the build filter, and docs/IMPORT_PIPELINE_SPEC.md (especially its section 13 bank-statement categories and section 14 card-settlement exclusion) as input, produce docs/CATEGORY_TAXONOMY.md: the finalized default v0.0.1 category taxonomy. Reconcile the coarse bank-statement cash-flow categories (Income, Incoming transfer, Outgoing transfer, Credit card payment / settlement, Loan payment, Interest / bank fee, Cash deposit / withdrawal, Other bank movement) with the future consumer-spending categories that itemized credit-card imports will need, keeping the two layers cleanly separated so card settlements are never double-counted. Define each category's purpose, what belongs in it, what does not, parent/child structure if any, system-default vs user-created handling, the uncategorized/Other policy (no dumping ground), and which categories are excluded from consumer-spending totals. Keep it small and justified; align with the 5-second-Home principle and v0.0.1 scope. Planning only, no code."

# Money App — Merchant Normalization Spec (v0.0.1, manual-first)

Status: Planning / specification only. No code, no DB migrations, no UI. This document defines how a user-typed merchant (and, later, an imported raw description) collapses to one stable normalized payee, how that payee suggests a category, and how user corrections stay authoritative.
Owner: backend-api-engineer (lead), with fintech-researcher and product-architect.
Governing decision: docs/MANUAL_FIRST_MVP_REVISION.md (2026-06-14) — v0.0.1 is manual-first; fast Quick Add is the primary loop.
Inputs (all read): docs/PRD_V0_1.md, docs/MANUAL_FIRST_MVP_REVISION.md, docs/CATEGORY_TAXONOMY.md (esp. §9 corrections & precedence, §6/§7 bank cash-flow + exclusions, the 14 consumer categories), docs/IMPORT_PIPELINE_SPEC.md (esp. §10 description/counterparty normalization, §12 dedup, §14 card-settlement exclusion).
Firm invariants carried forward unchanged: signed integer minor units + currency code; UTC for metadata timestamps only (financial dates are date-only); user_id on every user-owned row; raw transactions in SQL only and never embedded; the `is_card_settlement` exclusion flag keeps bank settlements out of consumer-spending totals; raw merchant text and raw descriptions are sensitive PII and are NEVER logged.
Scope discipline: deterministic rules + explicit user-confirmed aliases only. NO machine learning, NO fuzzy auto-merge. Anything labelled "assumption" is a product judgement by the author, not an established fact.
Date: 2026-06-14

---

## 1. Purpose

Merchant normalization exists in manual-first v0.0.1 so that the founder (the sole user) can log a purchase in under five seconds and have the app recognize a merchant they have used before — even when they type it slightly differently — and reuse what it already learned about that merchant.

Two concrete payoffs justify this work:

1. Faster Quick Add. As the user types a merchant, the app suggests recent/known merchants for one-tap selection. Recognizing "golda", "Golda", and "גולדה" as the same payee means the user taps one suggestion instead of re-typing and instead of accidentally creating three rival merchants.
2. Smarter category suggestions. Once a merchant is recognized, the app pre-fills the category from that merchant's history (a CategoryRule or recent-merchant memory, CATEGORY_TAXONOMY §9). The user confirms in one tap rather than picking from scratch.

Why this is MORE urgent under manual-first than under import-first: the merchant the user types by hand — with typos, partial names, and Hebrew/English variants — is now the PRIMARY key for autocomplete and auto-categorization, not a parsed bank description. If merchant identity fractures, the whole learning loop (recent merchants, merchant-to-category memory, CategoryRule matching, category totals) fractures with it. So merchant identity must be stable, deterministic, and under the user's control.

What this spec is NOT: it is not a clever matcher. v0.0.1 deliberately prefers a few correct, high-confidence recognitions plus explicit user-confirmed aliases over an ML model that guesses. A wrong silent merge corrupts spending analytics; a missed merge merely means the user types a name again. The asymmetry of harm dictates a conservative design.

---

## 2. Core definitions

These terms are used precisely throughout. The key distinction is: what the user TYPED vs what the app DISPLAYS vs what the system MATCHES on.

- raw_merchant_input — the exact text the user typed into the merchant field, preserved verbatim (after only the safe Unicode hygiene in §4 steps 3-4: strip invisible/bidi chars, NFC). This is the audit source of truth for a manual entry; for a manual transaction it doubles as the `raw_description`. Sensitive; never logged.
- normalized_merchant_name (the matching/comparison key) — a deterministic, cleaned form of `raw_merchant_input` used ONLY for matching and dedup. Lower-cased for English, whitespace-collapsed, punctuation-canonicalized, Hebrew preserved. This is never shown to the user; it exists so "Golda", "golda ", and "GOLDA" all resolve to the same key `golda`.
- merchant_display_name — the human-facing name the app shows for a Merchant (e.g. "Golda", "Wolt", "שופרסל"). Chosen from the raw input that first created the merchant or set explicitly by the user. The user can rename it; renaming changes display only, never the matching key or history.
- merchant_alias — an alternate raw form that maps to the SAME Merchant (e.g. "גולדה" as an alias of the "Golda" merchant; "WOLT TEL AVIV" as an alias of "Wolt"). Each alias carries a source, a confidence, and timestamps (§6). Aliases are how variant spellings collapse to one payee without guessing.
- merchant_candidate — a proposed (not yet confirmed) merchant identity produced from a raw input that did not confidently match an existing merchant. A candidate is surfaced as a suggestion or becomes a new merchant on save; it is never a silent merge into an existing merchant.
- merchant_confidence — the match-confidence level (§7 enum) describing how strongly a raw input matched an existing merchant: exact, alias_exact, normalized_exact, recent_suggestion, contains, fuzzy_possible, none. It governs whether the app auto-selects, only suggests, asks for confirmation, or creates a new merchant.
- category suggestion — the category the app pre-fills once a merchant is chosen, resolved by the precedence in §9 (user_correction merchant_exact > user_correction contains > system merchant_exact > system contains > recent-merchant memory > merchant default > uncategorized).
- CategoryRule relationship — a Merchant is the anchor for CategoryRules (CATEGORY_TAXONOMY §9). A confirmed "Always categorize [Merchant] as [Category]?" creates/updates a `merchant_exact` rule keyed to the merchant's normalized name; matching the merchant then resolves the category through that rule. Aliases let a rule fire even when the user typed a variant.

The mental model: raw_merchant_input is what the user typed; normalized_merchant_name is the fingerprint the system matches on; merchant_display_name is what the user sees back; aliases are the set of variants that share one fingerprint; confidence decides what the app does with a near-fingerprint.

---

## 3. Manual-first normalization goals

In priority order, normalization must:

1. Recognize obvious repeats. If the user has logged "Golda" before and types "golda" again, recognize it as the same merchant. This is the single most valuable behavior.
2. Suggest recent/known merchants while typing. Surface the user's own recent and frequent merchants as one-tap autocomplete suggestions (MANUAL_FIRST_MVP_REVISION §6).
3. Suggest a category from merchant history. When a known merchant is chosen, pre-fill its category (§9) so the user confirms rather than picks.
4. Let the user save quickly. Nothing in normalization may block or slow the sub-five-second save. Matching is best-effort; a save always proceeds.
5. Let the user correct merchant and category. The user can rename a merchant, split a wrongly-merged merchant, merge two merchants they consider the same, and re-point a category. User actions override automatic normalization, always.
6. Avoid dangerous over-merging. Never silently combine two merchants on weak evidence (§7, §12). When unsure, keep them separate or ask.
7. Preserve the raw typed value for auditability. The exact `raw_merchant_input` is retained so a wrong normalization can always be traced back and undone. Normalization is additive metadata; it never destroys the original.

Non-goals for v0.0.1: clever transliteration matching, phonetic matching, ML embeddings, automatic cross-merchant clustering, natural-language "Golda 33" parsing (architected-for later, not built — MANUAL_FIRST_MVP_REVISION §6).

---

## 4. Normalization pipeline

A simple, DETERMINISTIC pipeline turns `raw_merchant_input` into `normalized_merchant_name` (the matching key). It reuses the description-normalization rules already defined in IMPORT_PIPELINE_SPEC §10 so manual and imported text normalize identically. Given the same input, it always yields the same key (no randomness, no order-dependence).

Steps, in order:

1. Trim leading/trailing whitespace.
2. Collapse internal runs of whitespace to a single space.
3. Strip Unicode invisible/zero-width and bidi control characters (e.g. U+200B, U+200E, U+200F, U+202A-U+202E, U+FEFF). These are common in copy-paste and RTL text and would otherwise break equality.
4. Apply Unicode NFC so Hebrew (and accented Latin) composes consistently.
5. Case-fold English/Latin letters to lower case. Hebrew has no case; it is left unchanged (case folding Hebrew is meaningless and risky — IMPORT_PIPELINE_SPEC §10).
6. Canonicalize punctuation/quotes where safe: normalize Hebrew gershayim/geresh and ASCII quote variants to a canonical form; normalize different dash characters to a single hyphen. Do NOT delete punctuation that may carry meaning.
7. Remove obvious payment-noise tokens ONLY when unambiguously safe and only as a SEPARATE, conservative pass that produces the matching key without touching the raw or display value. Safe noise (assumption, conservative list): a leading/trailing city qualifier the user explicitly separated is NOT stripped here (branch words are meaningful — see step 8); generic acquirer prefixes that never appear in manual entry are out of scope for v0.0.1 (they belong to import). For manual input the safe-noise pass is intentionally minimal: collapse whitespace and case only. When unsure, keep the token.
8. Do NOT remove meaningful branch/location words (e.g. "Golda Givatayim", "Wolt Tel Aviv") during key construction unless the confidence rules in §7/§12 explicitly allow treating them as the same merchant. Branch may matter; stripping it risks over-merging two real businesses.

Outputs of the pipeline:
- `raw_merchant_input` — preserved verbatim after only steps 3-4 (invisible/bidi strip + NFC), exactly as IMPORT_PIPELINE_SPEC §10 preserves `raw_description`. Never altered for display convenience.
- `normalized_merchant_name` — the full pipeline result (steps 1-7), used for matching and dedup.

The same normalization function is reused for: merchant matching, alias matching, recent-merchant autocomplete comparison, and the manual-transaction dedup considerations. One function, one behavior, everywhere.

Privacy: both `raw_merchant_input` and `normalized_merchant_name` are sensitive and are NEVER logged (§14).

---

## 5. Hebrew/English handling

Israeli merchants appear in Hebrew, English, and mixed forms. The pipeline (§4) is Hebrew-safe by construction: it never case-folds, transliterates, or reorders Hebrew. Handling per case:

- Hebrew names — e.g. "שופרסל", "גולדה". Normalized by whitespace/invisible-char/NFC only; matched against other Hebrew forms exactly-after-normalization.
- English names — e.g. "Wolt", "Shufersal". Case-folded so "WOLT", "Wolt", "wolt" share key `wolt`.
- Mixed Hebrew-English — e.g. "Golda גבעתיים", "וולט Tel Aviv". Each script segment is normalized by its own rules (English segment case-folded, Hebrew segment preserved); the whole string is whitespace-collapsed and NFC-applied. No script is dropped.
- Transliteration variants — e.g. "Golda" vs "גולדה", "Wolt" vs "וולט", "Shufersal" vs "שופרסל". These do NOT share a normalized key; they are different scripts. v0.0.1 does NOT attempt to match across transliteration automatically. Instead, the link is made by an explicit user-confirmed ALIAS (§6): the first time the user has both, they confirm "same as Golda?" and an alias is stored. This is a firm decision (see below).
- Final-letter / spelling variants — Hebrew final letters (ך/כ, ם/מ, ן/נ, ף/פ, ץ/צ) and minor spelling differences are NOT auto-normalized in v0.0.1. Treating "מנוי" and a final-letter variant as identical is a heuristic that can over-merge; we prefer an explicit alias if it ever matters. (Assumption: final-letter folding is deferred; revisit only if the founder reports real friction.)

Examples (illustrative; confidence and category in §15):
- גולדה / Golda / גולדה גבעתיים — Golda is an ice-cream/dessert chain. Hebrew and English forms link only via a user-confirmed alias; the branch form "גולדה גבעתיים" is treated under §12 (branch may matter) — suggested as related, not silently merged.
- Wolt / וולט — food delivery; English and Hebrew forms link via a user-confirmed alias.
- Shufersal / שופרסל — supermarket; same.

FIRM DECISION: v0.0.1 does NOT require perfect transliteration matching. Cross-script and cross-spelling links are made by explicit, user-confirmed aliases, never by clever guessing. Rationale: transliteration is genuinely ambiguous (וולט could be "Wolt" or "Volt"), and a wrong silent cross-script merge corrupts analytics. An explicit alias is one extra tap the first time and is permanently correct thereafter.

---

## 6. Alias model

A Merchant can have many aliases. An alias is an alternate raw form that resolves to the same Merchant, enabling variant spellings and cross-script forms to collapse to one payee without guessing.

Alias sources and trust (highest trust first):
1. user_confirmed — the user explicitly said "this is the same merchant" (e.g. confirmed "גולדה is the same as Golda", or renamed/merged). Highest trust. Authoritative.
2. import_parsed — derived from a parsed bank/card description in a future import (v0.0.2+). Medium trust; an imported raw description does NOT automatically become a trusted alias without review (§11).
3. system_suggested — a normalized form the system proposes as probably-the-same (e.g. an exact normalized-key match that produced a recent-merchant suggestion). Lowest trust until the user acts on it.

Each alias stores (fields enumerated for the schema in §13; not a migration):
- the alias raw text and its normalized key,
- `source` (user_confirmed | import_parsed | system_suggested),
- `confidence` (the §7 match level under which it was created, or a trust marker for user_confirmed),
- `created_at` (UTC),
- `last_seen_at` (UTC) — updated whenever the alias is matched again, powering recency-based autocomplete ranking.

Trust rules:
- A user_confirmed alias OUTRANKS any system_suggested or import_parsed alias for the same text. The user is always authoritative (PRD principle 5; CATEGORY_TAXONOMY §9).
- A system_suggested or import_parsed alias is a candidate until the user uses or confirms it; it must never cause a silent merge of two distinct existing merchants.
- Alias matching supports BOTH autocomplete (an alias is a typeable handle that surfaces its merchant) AND category suggestion (matching via an alias resolves the merchant, then the merchant's category per §9).

The canonical exact form (the merchant's own `normalized_merchant_name`) is effectively the primary, highest-trust alias; additional aliases are alternates around it.

---

## 7. Matching confidence levels

When a raw input is entered, the app computes a single `merchant_confidence` level and acts on it. ONLY high-confidence levels auto-select an existing merchant; everything weaker is a SUGGESTION the user must choose, never a silent merge.

Levels, strongest to weakest, with the action for each:

1. exact — `raw_merchant_input` equals an existing merchant's stored raw/display form after normalization (identical normalized key AND same script).
   - Action: AUTO-SELECT the existing merchant. No new merchant, no prompt. Category pre-filled per §9.

2. alias_exact — the normalized input exactly matches an existing user_confirmed alias of a merchant.
   - Action: AUTO-SELECT that merchant (a user_confirmed alias is as trusted as exact). Category pre-filled per §9.

3. normalized_exact — the normalized key matches an existing merchant's normalized key, but the raw forms differed only by case/whitespace/punctuation (same script). E.g. "golda " vs "Golda".
   - Action: AUTO-SELECT the existing merchant. Optionally store the new raw form as a low-noise alias (system_suggested) so display history is preserved. Safe because same-script normalized equality is deterministic and not a transliteration guess.

4. recent_suggestion — the input is a prefix/typed-fragment of one or more of the user's recent/frequent merchants (autocomplete while typing).
   - Action: SUGGEST those merchants as tap-to-select options. Selecting one is the user's explicit choice (becomes exact/alias going forward). No auto-select without a tap.

5. contains — the normalized input contains, or is contained by, an existing merchant's normalized key as a whole-token relationship (e.g. typed "wolt tel aviv" vs existing "wolt"), OR a system/user `contains` CategoryRule fragment matches.
   - Action: SUGGEST the candidate merchant for confirmation ("Same as Wolt?"). Never auto-merge — a contains relationship can be a different business (e.g. "Cafe Cafe" vs "Cafe"). On confirm, store an alias.

6. fuzzy_possible — a near-but-not-equal normalized similarity (e.g. a one-character typo). v0.0.1 does NOT compute fuzzy distance automatically; this level exists only as a placeholder for a possible future, conservative typo hint. In v0.0.1 it behaves as `none` unless a deterministic cheap signal (shared exact prefix surfaced by recent_suggestion) already covers it.
   - Action (v0.0.1): treat as `none` (create-new path) unless the user picked a recent suggestion. No silent fuzzy merge, ever.

7. none — no acceptable match.
   - Action: CREATE A NEW MERCHANT from the raw input on save (a fresh merchant_candidate that becomes a Merchant). Category defaults to uncategorized unless the user picks one.

Firm rules across all levels:
- Auto-select ONLY at exact, alias_exact, normalized_exact. These are deterministic, same-script identities.
- Suggest (require a tap) at recent_suggestion and contains.
- Never silently merge at contains, fuzzy_possible, or across scripts (§5). A cross-script link requires a user_confirmed alias.
- Save is never blocked: if the user ignores all suggestions and saves, the system uses the create-new path (none) rather than forcing a match.

---

## 8. Quick Add behavior

Quick Add is the primary v0.0.1 loop and must stay under five seconds (MANUAL_FIRST_MVP_REVISION §6). Merchant normalization serves it as follows:

- User starts typing the merchant. As characters arrive, the app shows recent/frequent merchant suggestions (recent_suggestion, §7), ranked by recency (`last_seen_at`) and frequency. Selecting one is one tap and yields an exact/alias-level match going forward.
- Selecting a merchant auto-suggests its default category. On selection, the category is pre-filled per §9 (rule > memory > merchant default). The user confirms or overrides in one tap; for a repeat merchant they typically never open the category picker.
- Amount-first flow support. The amount field is focused with the keypad up on open (MANUAL_FIRST_MVP_REVISION §6). Merchant matching runs asynchronously as the user types the merchant and must never block the amount entry or the save button.

FIRM DECISION — merchant is OPTIONAL, not required. The app MUST allow an amount-only save (amount + today's date), with merchant left blank and category defaulting to uncategorized. Rationale: the fatal risk for manual-first is the user not logging at all (MANUAL_FIRST_MVP_REVISION §12). Forcing a merchant adds friction to the exact moment we most need to be frictionless. A blank-merchant, uncategorized transaction is a first-class, correctable state (CATEGORY_TAXONOMY §8) — better a fast incomplete entry than no entry. The user can add the merchant/category later.

Consequences of the optional-merchant decision:
- An amount-only save creates a transaction with `merchant_id = null` and `category_id = null` (uncategorized). It counts toward the month's actual-spend total (it is real spend) and is surfaced in the "needs a category" review (CATEGORY_TAXONOMY §8).
- Fallback when a merchant is typed but unmatched: create a new merchant (none, §7); the user may still leave category as uncategorized or pick `other_spending` if they want it "done" (CATEGORY_TAXONOMY §11). Uncategorized is preferred when they expect to fix it later; `other_spending` when they want closure. Neither blocks the save.
- Keep entry under five seconds: the happy path is amount → tap a recent merchant (category auto-fills) → save. Matching, suggestion, and rule lookup all happen in the background and never gate the save.

---

## 9. Category suggestion behavior

Once a merchant is resolved (or typed), the app suggests a category. The resolution order is the CategoryRule precedence from CATEGORY_TAXONOMY §9, restated here as the authoritative ladder:

Precedence (highest first):
1. user_correction `merchant_exact` — a rule the user confirmed for this merchant. Strongest, least noisy.
2. user_correction `contains` — a user fragment rule (e.g. "WOLT").
3. system `merchant_exact` — a seeded exact rule (rare in v0.0.1; mostly user-driven).
4. system `contains` — a seeded fragment rule.
5. recent-merchant memory — the category last used for this merchant, remembered even before a formal rule exists (the lightweight no-friction path).
6. merchant default — the merchant's `default_category_id`, if set.
7. uncategorized — `category_id = null` if nothing above resolves.

Behavior:
- The first level that resolves wins; lower levels are not consulted.
- The suggested category is PRE-FILLED, not committed silently as final — the user can override in one tap, and the override always wins (PRD principle 5).
- Most-used category for this merchant: when multiple historical categories exist for a merchant without a confirmed rule, recent-merchant memory uses the most-recently-used; the most-FREQUENT may be offered as a secondary chip (assumption: recency leads, frequency is a tiebreaker). A confirmed correction promotes the choice to a `merchant_exact` rule.
- A user override at save time updates recent-merchant memory for the merchant immediately; whether it becomes a permanent rule depends on the explicit "Always categorize…?" confirmation (§10).
- Bank-movement (Layer C) categories are NEVER suggested in manual Quick Add (CATEGORY_TAXONOMY §11). Only the 14 Layer A consumer categories (plus uncategorized) are offered.

---

## 10. CategoryRule integration

Merchant normalization is the anchor for CategoryRules (CATEGORY_TAXONOMY §9; PRD §11). Rule types and integration:

- merchant_exact — keyed to a merchant's `normalized_merchant_name`. Created/updated when the user confirms "Always categorize [Merchant] as [Category]?". The primary, least-noisy rule type.
- merchant_contains — keyed to a description/raw fragment (e.g. "WOLT" matching "WOLT TEL AVIV"). Lower precedence than exact because it can over-match. Most useful for future imported raw descriptions (§11), but available for manual fragments too.
- alias-based matching — because aliases resolve to the merchant, a `merchant_exact` rule fires for ALL of a merchant's aliases. The rule is keyed to the merchant (via its normalized name), so confirming a rule once covers "Golda", "golda", and a user-confirmed "גולדה" alias together. This is the chief reason aliases and rules are designed together.
- priority — resolved by the §9 precedence ladder; ties broken by most-recently-updated (the newer correction reflects current intent, CATEGORY_TAXONOMY §9).
- system rule vs user correction — `source = user_correction` always outranks `source = system`. User choice is authoritative.

Conflict handling:
- If a new user correction conflicts with an existing user rule for the SAME merchant, UPDATE the existing rule (a merchant maps to exactly one category at a time), never stack a second rival rule (CATEGORY_TAXONOMY §9).
- If two different rules (e.g. an exact and a contains) could match, the higher-precedence one wins per §9.
- Rules apply going forward by default; bulk re-categorization of past transactions is an explicit, optional, user-initiated action, never automatic.

When the app asks "Always categorize this merchant as X?":
- On a category change/correction for a merchant that does not yet have a confirmed `merchant_exact` rule, AND the merchant is a real recognized payee (not blank, not a one-off `other_spending`), offer the prompt. A "yes" creates/updates the `merchant_exact` rule; a "no" changes only this transaction and updates recent-merchant memory.

When NOT to create a rule automatically:
- Never from a silent edit without the explicit confirmation — a single edit changes only that transaction (CATEGORY_TAXONOMY §9). Rules are opt-in so the user is never surprised by future auto-categorization.
- Never for a one-off `other_spending` entry — wait for the repeat threshold (CATEGORY_TAXONOMY §8).
- Never create a `contains` rule from a very short or generic fragment (e.g. "cafe", "bit", "market", "transfer") — these over-match unrelated merchants (§12). A minimum-length / non-generic check applies (assumption: short/generic fragments are rejected as rule values).
- Never for a blank-merchant transaction (there is no merchant to key a rule to).

---

## 11. Future import compatibility

v0.0.1 is manual-first, but the merchant model must let v0.0.2 bank cash-flow import and v0.0.3 itemized card import reuse the same merchant identity without corrupting analytics. Design rules:

- Bank statement descriptions are noisier and create merchant candidates carefully. A parsed `normalized_counterparty` (IMPORT_PIPELINE_SPEC §10) may PROPOSE a merchant candidate, but it does not silently merge into an existing manual merchant. Bank descriptions are often operational text, not clean payee names.
- Itemized card imports (v0.0.3) may include cleaner merchant names per purchase. These are better candidates for Layer A consumer merchants than bank descriptions, but still go through the same confidence ladder (§7) and never silently merge across scripts.
- Imported raw descriptions do NOT immediately become trusted aliases. An import-parsed alias has `source = import_parsed` and medium trust; it requires user review/use before it is treated as a confirmed alias (§6). This prevents a noisy bank string from permanently mislabeling a merchant.
- Credit-card settlements do NOT become consumer merchants. A row with `is_card_settlement = true` (IMPORT_PIPELINE_SPEC §14; CATEGORY_TAXONOMY §6/§7) is a Layer C cash-flow movement to the card issuer. It must never be turned into a consumer Merchant and must never appear in merchant autocomplete or category-spend rankings. Issuer names (Isracard/Max/Cal) are settlement counterparties, not places the user shopped.
- Imported and manual merchants reconcile through aliases and confidence. When a future import produces a payee that matches an existing manual merchant at exact/alias_exact/normalized_exact (same script), it links; at contains it is suggested for confirmation; across scripts it requires a user-confirmed alias. The same CategoryRule then applies regardless of `source` (CATEGORY_TAXONOMY §13). v0.0.1 does NOT auto-reconcile a manual purchase against a later imported card purchase of the same money (out of scope); only the settlement exclusion prevents the settlement-vs-manual double count.

---

## 12. Anti-overmerge rules

The single most important correctness rule: never merge two merchants on weak evidence. A wrong merge silently corrupts spending analytics; a missed merge merely costs a retype. When unsure, create a separate merchant OR ask the user.

The app MUST NOT merge automatically in these cases:

- Similar text, different business. "Cafe Cafe" vs "Cafe Greg"; "Max" the brand vs "Max" the card issuer; "Golda" vs "Golда"-with-Cyrillic-lookalike. A shared substring is not identity.
- Merchant + different branch, when branch may matter. "Golda Givatayim" vs "Golda Dizengoff" — the user may genuinely want per-branch visibility, or may want them merged. Default: treat the base name as a candidate link and SUGGEST ("same as Golda?"), do not auto-merge. The user decides whether branches collapse.
- Generic names. "Market", "Cafe", "Kiosk", "Makolet", "Paybox", "Bit", "Transfer", "ATM" — these are too generic to be a merchant identity or a `contains` rule value. They must not anchor an auto-merge or an auto-rule (§10). (Assumption: a small generic-token denylist guards rule creation and contains-matching.)
- Card settlements (Isracard / Max / Cal). Never consumer merchants (§11). They are Layer C settlement counterparties with `is_card_settlement = true`, excluded from spend.
- Bank operation descriptions. "העברה יוצאת", "חיוב כרטיס אשראי", "עמלה", "ריבית" — these are bank-movement descriptions (Layer C), not consumer merchants. They never become Quick Add merchants.
- Ambiguous Hebrew/English variants. "וולט" → "Wolt" or "Volt"? "פז" → "Paz" or a person's name? Cross-script links require an explicit user-confirmed alias (§5), never an automatic transliteration merge.

When unsure: prefer creating a SEPARATE merchant (the user can merge later) over an automatic merge (which the user must notice and unwind). If a link is plausible (contains, same base name, cross-script with a near-obvious counterpart), SUGGEST it and let the user confirm. Silence-on-doubt means separate, not merged.

Paybox / Bit specifically: these are peer-to-peer transfer apps, not merchants the user "spent at." A manual entry the user types as "Paybox"/"Bit" is treated as a generic transfer-like payee and must NOT auto-anchor a spending merchant or a rule; if logged manually as actual spend (e.g. money the user considers a gift), the category is the user's choice (e.g. `gifts`), but the merchant identity stays low-trust and is never auto-merged. A future bank-imported Paybox/Bit line is Layer C cash-flow, separate from any manual spend (CATEGORY_TAXONOMY §7).

---

## 13. Data model implications

This section states what the schema must SUPPORT (owned by DATABASE_SCHEMA_V0_0_1.md). It is NOT a migration and NOT a full schema. All rows carry `user_id` for isolation; metadata timestamps are UTC; money (where relevant elsewhere) is signed integer minor units.

Merchant must support:
- `id`, `user_id` (isolation).
- `normalized_merchant_name` — the matching key (§4); indexed per user for fast exact/normalized lookup. (Aligns with PRD/MANUAL_FIRST `normalized_name`.)
- `display_name` (merchant_display_name) — human-facing, user-renamable.
- `raw_merchant_input` preservation — the original typed value that created the merchant, retained for audit (may live as the first alias rather than a separate column; the schema decides).
- `default_category_id` (nullable) — the merchant default used at §9 level 6.
- `created_at`, `updated_at` (UTC).
- Notes: a merchant with no category default is fine; uncategorized is first-class.

MerchantAlias must support:
- `id`, `user_id`, `merchant_id` (the merchant it resolves to).
- alias raw text and `normalized_alias_key` (indexed per user for alias_exact lookup).
- `source` (user_confirmed | import_parsed | system_suggested) — user approval marker.
- `confidence` — the §7 level / trust marker under which it was created.
- `created_at`, `last_seen_at` (UTC) — recency for autocomplete ranking.
- Notes: aliases are how variant/cross-script forms collapse to one merchant; user_confirmed outranks others. (This generalizes the PRD/MANUAL_FIRST `raw_aliases` array into first-class rows so source/confidence/timestamps can be stored.)

CategoryRule must support (consistent with CATEGORY_TAXONOMY §9, PRD §11):
- `id`, `user_id`, `match_type` (merchant_exact | contains), `match_value` (the merchant's normalized name for exact, or a fragment for contains), `category_id`, `priority`, `source` (system | user_correction), `created_at`.
- Notes: a `merchant_exact` rule keyed to the merchant's normalized name fires for all that merchant's aliases (§10).

Transaction (relevant fields only; full entity owned by the schema doc):
- `merchant_id` (nullable — amount-only saves), `category_id` (nullable — uncategorized first-class), `raw_description` (for a manual entry, the `raw_merchant_input`), `source` (manual | bank_import), `is_card_settlement` (default false), `dedup_hash` (nullable for manual; required/unique for imported).

The schema must NOT bake in: transliteration tables, fuzzy-distance indexes, or any ML artifact. None are used in v0.0.1.

---

## 14. Privacy and logging

Merchant data is sensitive spending behavior: knowing where someone shops reveals habits, health, beliefs, and relationships. It is treated as PII (PRD §15; CATEGORY_TAXONOMY invariants).

MUST NEVER be logged:
- `raw_merchant_input` (the typed merchant text).
- `raw_description` / `normalized_counterparty` from imports.
- `normalized_merchant_name` or any alias text (still reveals the merchant).
- `display_name` of a merchant.
- Amounts tied to identity, including per-transaction amounts.
- Any combination that re-identifies a merchant or purchase.

SAFE to log (structured, IDs / counts / enums only — never raw text):
- `merchant_id`, `alias_id`, `category_id`, `rule_id`, `user_id` (an opaque id, not an email).
- Counts (e.g. number of merchants matched, number of suggestions shown).
- `merchant_confidence` LEVEL as an enum (exact | alias_exact | normalized_exact | recent_suggestion | contains | fuzzy_possible | none) — the level name only, never the text that produced it.
- match-type and rule `source`/`match_type` enums.
- Event types and success/failure status.

Handling raw merchant input: stored in SQL (sensitive), shown in-app to the owner, never logged, never embedded (raw transactions in SQL only — firm invariant). It is treated as untrusted DATA, never as instructions to any future LLM step (PRD §13).

Handling imported descriptions: same as IMPORT_PIPELINE_SPEC §17 — stored in SQL, shown to the owner, never logged, never embedded; treated as untrusted data.

Debugging matching without exposing PII: debug by IDs and confidence-level enums, e.g. "input matched merchant_id=… at level=normalized_exact; suggested rule_id=…; 3 recent suggestions shown." This is enough to trace a wrong match without ever logging the merchant text. If a developer needs to see the text, they read it from SQL as the data owner in a controlled context, never from logs.

Why this matters: a leaked log of merchant names is a leaked spending profile. The no-text-in-logs rule is absolute.

---

## 15. Examples

Worked examples. Columns: raw input → normalized key → suggested merchant → confidence (§7) → suggested category (CATEGORY_TAXONOMY snake_case) → user confirmation required?

1. Golda / גולדה / גולדה גבעתיים
- "Golda" → `golda` → new merchant "Golda" (first time) → none → uncategorized until user picks `eating_out` → no merge needed; user may set category.
- "golda" (later) → `golda` → existing "Golda" → normalized_exact → `eating_out` (from memory/rule) → AUTO-SELECT, no confirmation.
- "גולדה" → `גולדה` → candidate; cross-script from "Golda" → none (no auto cross-script) → suggest "Same as Golda?" → CONFIRMATION REQUIRED to create a user_confirmed alias; thereafter auto-selects.
- "גולדה גבעתיים" → `גולדה גבעתיים` → base name links to "גולדה"/Golda but branch differs → contains → SUGGEST "Same as Golda?" → CONFIRMATION REQUIRED (branch may matter, §12).

2. Wolt / וולט / WOLT TEL AVIV
- "Wolt" → `wolt` → "Wolt" → exact (if exists) → `eating_out` → AUTO-SELECT.
- "וולט" → `וולט` → cross-script candidate → none → suggest "Same as Wolt?" → CONFIRMATION REQUIRED (could be "Volt", §5/§12).
- "WOLT TEL AVIV" → `wolt tel aviv` → contains "wolt" → contains → SUGGEST "Same as Wolt?" → CONFIRMATION REQUIRED; on confirm, store alias (relevant chiefly for future imports, §11).

3. Shufersal / שופרסל
- "Shufersal" → `shufersal` → "Shufersal" → exact → `groceries` → AUTO-SELECT.
- "שופרסל" → `שופרסל` → cross-script candidate → none → suggest "Same as Shufersal?" → CONFIRMATION REQUIRED to link via user_confirmed alias.

4. Gett / GETT TAXI
- "Gett" → `gett` → "Gett" → exact → `transport` → AUTO-SELECT.
- "GETT TAXI" → `gett taxi` → contains "gett" → contains → SUGGEST "Same as Gett?" → CONFIRMATION REQUIRED.

5. Paz / פז
- "Paz" → `paz` → "Paz" → exact → `car_fuel` → AUTO-SELECT.
- "פז" → `פז` → cross-script candidate, and "פז" is short/ambiguous → none → suggest "Same as Paz?" → CONFIRMATION REQUIRED (short Hebrew token; never auto-merge, §12).

6. Apple / Apple.com / Apple Services
- "Apple" → `apple` → "Apple" → exact → `shopping` or user's choice → AUTO-SELECT if exists.
- "Apple.com" → `apple.com` → not identical key to `apple` (punctuation/domain differs) → contains/none → SUGGEST "Same as Apple?" → CONFIRMATION REQUIRED (could be App Store vs hardware; user decides).
- "Apple Services" → `apple services` → contains "apple" → contains → SUGGEST → CONFIRMATION REQUIRED. (User may prefer to keep Apple hardware vs Apple subscriptions distinct: `shopping` vs `subscriptions`.)

7. Isracard / Max / Cal — card settlements, NOT consumer merchants
- "Isracard" / "Max" / "Cal" as a bank-imported settlement line (`is_card_settlement = true`) → category `credit_card_settlement` (Layer C) → NOT a consumer merchant → NEVER in autocomplete, NEVER in spend totals → no consumer-merchant created; confirmation not applicable (excluded by construction, §11/§12).
- Note: if the user MANUALLY types "Max" meaning the fashion store, that is a separate, legitimate consumer merchant — but the app does not auto-link it to the issuer; they are different businesses (§12).

8. Paybox / Bit — transfers, NOT automatic merchant spending
- "Paybox" / "Bit" → `paybox` / `bit` → generic transfer-like payee → treated as low-trust, generic (§12) → NOT auto-anchored as a spending merchant, NOT used to auto-create a rule → if the user logs it as actual spend, category is the user's explicit choice (e.g. `gifts`); CONFIRMATION effectively required for any category, and no auto-merge/rule. A future bank-imported Paybox/Bit line is Layer C cash-flow, separate from manual spend (§11).

---

## 16. Test cases

Each gives an input condition and the expected behavior. No code; these define acceptance for the matcher.

1. Exact merchant match — Input: user has merchant "Wolt"; types "Wolt". Expected: confidence=exact; auto-select "Wolt"; category pre-filled from §9; no new merchant; no prompt.

2. Hebrew alias match — Input: "גולדה" is a user_confirmed alias of "Golda"; user types "גולדה". Expected: confidence=alias_exact; auto-select "Golda"; category from the merchant's rule/memory; no prompt.

3. English alias match — Input: "WOLT TEL AVIV" is a user_confirmed alias of "Wolt"; user types it. Expected: confidence=alias_exact; auto-select "Wolt"; no prompt.

4. Mixed Hebrew/English — Input: "Golda גבעתיים". Expected: normalized to `golda גבעתיים`; both scripts preserved; base "Golda" link surfaced as contains → SUGGEST confirmation; never silent merge.

5. Recent merchant autocomplete — Input: user types "gol" with recent merchants including "Golda". Expected: confidence=recent_suggestion; "Golda" offered as a one-tap suggestion ranked by recency/frequency; selecting it yields exact/alias going forward; no auto-select without a tap.

6. Category suggestion from merchant history — Input: user previously categorized "Aroma" as `eating_out` (recent-merchant memory, no formal rule yet); selects "Aroma". Expected: category pre-filled `eating_out` via §9 level 5; user can override in one tap.

7. User correction creates rule — Input: user changes a "Wolt" transaction to `eating_out` and confirms "Always categorize Wolt as Eating out?". Expected: a `merchant_exact` user_correction rule keyed to `wolt` is created/updated; future "Wolt" (and its aliases) auto-suggest `eating_out`; only this transaction changed if the user declines the prompt.

8. Conflicting rules — Input: a system `contains` rule "wolt"→`eating_out` and a user `merchant_exact` rule "Wolt"→`shopping` both could match. Expected: user_correction merchant_exact wins (§9); suggested category=`shopping`; ties (same level) broken by most-recently-updated.

9. Low-confidence fuzzy match — Input: user types "Goldaa" (typo) with merchant "Golda" existing. Expected: confidence behaves as none in v0.0.1 (no auto fuzzy merge); create-new path on save OR user picks "Golda" from a recent suggestion if surfaced by prefix; never a silent merge into "Golda".

10. Anti-overmerge case — Input: merchant "Golda Givatayim" exists; user types "Golda Dizengoff". Expected: contains link to base "Golda" → SUGGEST confirmation; NOT auto-merged; the two remain distinct unless the user confirms (branch may matter, §12).

11. Card settlement not treated as merchant spending — Input: a bank import lands a "חיוב כרטיס אשראי / Isracard" settlement (`is_card_settlement = true`). Expected: category `credit_card_settlement` (Layer C); no consumer Merchant created; excluded from spend totals and from autocomplete; visible only in cash-flow view.

12. Raw merchant not logged — Input: any Quick Add with logging enabled. Expected: logs contain only IDs, counts, and confidence-level/match-type enums; assert NO `raw_merchant_input`, NO alias text, NO `normalized_merchant_name`, NO `display_name`, NO amounts appear in any log line (§14).

Additional: amount-only save — Input: user enters amount 33, leaves merchant blank, saves. Expected: transaction persists with `merchant_id=null`, `category_id=null` (uncategorized), counts toward month spend, surfaced for later categorization; save succeeds in under five seconds.

---

## 17. Acceptance criteria

This spec is complete when ALL hold:

1. Manual Quick Add can safely suggest merchants (recent/frequent autocomplete) and categories (via §9 precedence) without blocking the sub-five-second save.
2. Obvious repeats are recognized: exact, alias_exact, and normalized_exact (same-script) auto-select an existing merchant deterministically.
3. Low-confidence matches do NOT silently merge: contains and cross-script are suggestions requiring user confirmation; fuzzy behaves as none in v0.0.1; generic/settlement/bank-operation names never auto-merge (§7, §12).
4. User corrections override system guesses: user_confirmed aliases and user_correction rules outrank system/import signals; the user can rename, merge, and split merchants, and override any category (§6, §9, §10).
5. CategoryRule integration is clear: a `merchant_exact` rule keyed to the merchant fires across its aliases; the "Always categorize…?" prompt and the when-NOT-to-create-a-rule rules are specified (§10).
6. Future imports can reuse merchant identity without corrupting spending analytics: imported descriptions become candidates, not trusted aliases, until reviewed; card settlements never become consumer merchants; reconciliation flows through aliases and the confidence ladder (§11).
7. The next DB schema can model Merchant and MerchantAlias without immediate revision: the §13 field list is seed/implementation-ready, generalizing PRD `raw_aliases` into first-class MerchantAlias rows with source/confidence/timestamps, all `user_id`-isolated, with no ML artifacts baked in.
8. Privacy holds: raw merchant input, alias text, normalized keys, display names, and amounts are never logged; only IDs/counts/enums are (§14).
9. The design uses deterministic rules + explicit user-confirmed aliases only — no ML, no fuzzy auto-merge.

---

## 18. Next recommended prompt

Firm recommendation: proceed to docs/QUICK_ADD_UX_SPEC.md next.

Justification: the build-filter sequence and the prior docs both point here. CATEGORY_TAXONOMY §15 and the import spec's chain set the order as taxonomy → merchant normalization → schema, but the manual-first pivot makes Quick Add the product's whole reason to exist, and three of the behaviors this spec defines — recent-merchant autocomplete, category auto-suggestion, and the "Always categorize…?" prompt — are UX flows that must be pinned down as concrete screens before the schema and API freeze around them. The merchant spec defined the LOGIC (confidence levels, alias confirmation, optional-merchant decision); QUICK_ADD_UX_SPEC must now define the FLOW (field order, keypad-up, suggestion timing, confirmation placement, the amount-only save, error/empty states) so that DATABASE_SCHEMA_V0_0_1 and API_CONTRACT_V0_0_1 are written against a settled interaction model rather than a guessed one. Drawing the schema first risks baking endpoints around a Quick Add flow that the UX then revises — the same trap the earlier docs warn about for categories.

I considered DATABASE_SCHEMA_V0_0_1.md coming first and reject it as premature, but with a caveat. The Merchant/MerchantAlias/CategoryRule shapes are now well-specified (§13), so the schema is LOW-risk to write. However, the optional-merchant decision (§8), the amount-only save, and the alias-confirmation flow each have small schema-adjacent implications (nullable `merchant_id`, first-class alias rows, the confirmation that promotes memory to a rule) that are cleaner to validate against a concrete Quick Add UX than to assume. If the founder prefers to unblock backend/database work immediately and is willing to accept minor schema revision after the UX lands, the schema can be written next instead — the §13 field list is deliberately seed-ready for exactly that. Net recommendation: do QUICK_ADD_UX_SPEC first (it is the manual-first heart and de-risks the schema), then DATABASE_SCHEMA_V0_0_1.md immediately after.

Exact next prompt to send after approving this spec:

> "Acting as the mobile-ux-designer agent with the product-architect agent, and using docs/PRD_V0_1.md as the long-term vision, docs/MANUAL_FIRST_MVP_REVISION.md as the governing v0.0.1 decision (especially §6 Quick Add UX requirements and §10 Home), docs/CATEGORY_TAXONOMY.md as the finalized taxonomy, and docs/MERCHANT_NORMALIZATION_SPEC.md as the merchant-matching logic, produce docs/QUICK_ADD_UX_SPEC.md for manual-first v0.0.1. Define the sub-five-second Quick Add flow as concrete low-fidelity screen specs: the one-tap entry point, amount-first focus with the keypad up, merchant autocomplete from recent/frequent merchants, category auto-suggestion from merchant history, the firm amount-only (merchant-optional) save defaulting to uncategorized, the date-defaults-to-today behavior, the 'Always categorize [Merchant] as [Category]?' confirmation placed behind the primary path, and the cross-script 'Same as Golda?' alias-confirmation prompt. For each screen/state define purpose, key elements, primary action, what is hidden behind progressive disclosure, validation, and empty/loading/error states. Keep it RTL-safe and neutral in tone, aligned with the firm invariants (signed minor units, UTC metadata, user_id everywhere, raw transactions never embedded, no PII in logs) and the no-ML/no-fuzzy-auto-merge merchant rules. Planning and design only, no code."

# Money App — Quick Add UX Specification (v0.0.1, manual-first)

Status: UX / product specification only. No code, no DB migrations, no UI components. This document defines the concrete sub-five-second Quick Add flow, its screen layout, states, microcopy, and the supporting Home integration for manual-first v0.0.1.
Owner: mobile-ux-designer (lead), with product-architect, backend-api-engineer, fintech-researcher, and security-privacy-engineer perspectives.
Governing decision: docs/MANUAL_FIRST_MVP_REVISION.md (2026-06-14) — v0.0.1 is manual-first; fast Quick Add is the primary loop.
Inputs (all read): docs/PRD_V0_1.md, docs/MANUAL_FIRST_MVP_REVISION.md (esp. §6 Quick Add UX, §7 recurring templates, §10 Home), docs/CATEGORY_TAXONOMY.md (14 consumer categories, §8 Other/Uncategorized policy, §11 Quick Add ordering, §12 Home labels), docs/MERCHANT_NORMALIZATION_SPEC.md (§7 confidence levels, §8 merchant-optional/amount-only save, §9 category suggestion, §10 "Always categorize?" prompt, cross-script "Same as Golda?" alias confirmation).
Firm invariants carried forward unchanged: merchant is OPTIONAL; amount-only save MUST work (merchant_id=null, category_id=null, date=today); actual spending and projected commitments stay separate and never blended without labels; recurring templates create NO actual transactions in v0.0.1; money = signed integer minor units + ILS default; UTC for metadata, financial dates date-only; user_id everywhere; raw transactions in SQL only, never embedded; never log merchant text/amount/note/raw input; no shame/guilt language; RTL-safe (logical start/end); no ML, no fuzzy auto-merge, no silent cross-script merge.
Anything labelled "assumption" is a product judgement by the author, not an established upstream fact.
Date: 2026-06-14

---

## 1. Purpose

Quick Add is the most important flow in v0.0.1. The manual-first pivot exists because there is no reliable, supported iOS MVP path to automatically capture Apple Pay / Wallet / FinanceKit transactions (MANUAL_FIRST_MVP_REVISION §1, PRD §6), and exporting multiple per-card files every month is too much friction for a tool meant to be used daily. With automatic capture off the table, the only way real consumer-spending data enters the app is the user typing a purchase by hand, in the moment.

That makes Quick Add the single point where the whole product succeeds or fails. If logging a purchase is faster than the user's resistance to doing it — sub-five-seconds, two or three taps — the habit forms, real category data accrues, merchant/category memory improves, and Home becomes useful. If Quick Add is even slightly too heavy, the user stops logging, the data dries up, and every later layer (bank cash-flow import, card import, insights, AI coach) has nothing real to stand on.

This spec therefore optimizes for one thing above all: the speed and emotional lightness of capturing a purchase. Manual entry must feel lighter than a spreadsheet — no formulas, no required fields beyond an amount, no chores. Everything else (merchant memory, category learning, recurring commitments, Home rollups) is built to serve that capture, never to slow it.

---

## 2. Core UX goal

A normal expense is saved in under five seconds.

Concretely:

- The realistic happy path is: tap "+" → amount field is already focused with the numeric keypad up → type the amount → (optionally) tap a recent merchant whose category auto-fills → tap Save. Two or three taps plus the amount.
- Amount-only entry is always possible. Typing "33" and tapping Save is a complete, valid transaction (amount, today's date, merchant_id=null, category_id=null). This is a first-class path, not a degraded one (MERCHANT_NORMALIZATION_SPEC §8).
- Merchant and category improve the data but never block saving. They make Home richer and teach the system, but the Save button is enabled the instant a valid amount exists.
- The user is never forced into a long form. Note, date change, and rule prompts live behind progressive disclosure. The user can ignore all of them forever and still get a working tracker.

The emotional goal is equally firm: entry is calm and judgement-free. No "you've spent a lot today," no red warnings, no nagging. The app's job at capture time is to get out of the way (PRD principle 8; CATEGORY_TAXONOMY principle 5).

---

## 3. Quick Add entry modes

Four modes describe the spectrum of how much the user fills in. Modes A–C all ship in v0.0.1 as the same single screen behaving differently based on what the user provides — they are not separate screens. Mode D is explicitly future.

### Mode A — Amount-only (the floor; must always work)

- Example: user types "33" and saves.
- Required: amount.
- Optional: nothing else touched.
- Save behavior: creates a transaction with `amount_minor` set, `posted_date = today`, `merchant_id = null`, `category_id = null` (uncategorized), `source = manual`. (MERCHANT_NORMALIZATION_SPEC §8.)
- After save: success confirmation; the transaction is real spend and counts toward the month total; it is added to the "needs a category" review surface (CATEGORY_TAXONOMY §8). No rule prompt (no merchant to key a rule to).
- Home effect: increases "Spent so far"; appears in Recent transactions labelled as uncategorized; contributes to the uncategorized review count.

### Mode B — Amount + merchant

- Example: user types amount 33, then "Golda" (or taps it from recent merchants).
- Required: amount.
- Optional but provided: merchant.
- Save behavior: resolves the merchant via the confidence ladder (MERCHANT_NORMALIZATION_SPEC §7). If a category is suggested from merchant history (rule/memory/default, §9), it is pre-filled and saved with the transaction unless the user clears it. If no category resolves, `category_id = null` (uncategorized).
- After save: success confirmation. If the merchant + a category were saved AND no trusted `merchant_exact` rule exists yet, a soft, non-blocking "Always categorize Golda as Eating out?" prompt may appear in the success state (§8). If the typed merchant is a cross-script/branch candidate, a "Same as Golda?" alias suggestion may appear (§8) — also non-blocking.
- Home effect: increases "Spent so far"; if categorized, contributes to that category's total and possibly Top category; the merchant becomes/refreshes a recent merchant for faster reuse.

### Mode C — Amount + merchant + category (fully categorized)

- Example: amount 33, "Golda", category Eating out (auto-filled and confirmed, or manually picked).
- Required: amount.
- Provided: merchant and category.
- Save behavior: a fully categorized actual transaction. If the category was a user override of the suggestion (or the first time for this merchant), the success state may offer the "Always categorize…?" prompt to promote it to a rule (§8, §10).
- After save: success confirmation; recent-merchant memory updates immediately; rule creation only on explicit confirmation.
- Home effect: cleanest case — increases "Spent so far", lands in the right category, strengthens Top-category accuracy, and improves future auto-suggestion.

### Mode D — Natural-language single-line ("Golda 33") — FUTURE, NOT v0.0.1

- Example: user types "Golda 33" and the app parses merchant=Golda, amount=33, category auto-suggested.
- Status: explicitly out of scope for v0.0.1 (MANUAL_FIRST_MVP_REVISION §6, MERCHANT_NORMALIZATION_SPEC §3). The entry model is architected so this can be added later without rework (amount and merchant are already discrete fields with discrete resolution), but no parser is built now.
- Why deferred: a parser introduces ambiguity ("Golda 33" vs "33 Golda" vs "Golda Givatayim 33") and an error class that undermines the trust the capture loop needs. Discrete fields are faster to get right and already hit the five-second target.

---

## 4. Primary screen layout

One screen, opened by a one-tap entry point (a persistent "+" / floating action button reachable from Home; no menu, no intermediate screen — MANUAL_FIRST_MVP_REVISION §6). Layout uses logical start/end, never hard-coded left/right (§14).

Above-the-keyboard zone (always visible, the primary path):

```
+---------------------------------------------------+
|  [x] Cancel                          Add expense   |   <- title, dismiss at logical start
|                                                    |
|              ₪  [ 33        ]                       |   <- AMOUNT, focused on open, large
|                  amount                            |
|                                                    |
|   [ Merchant (optional)            ]               |   <- merchant field, below amount
|   recent:  ( Golda ) ( Aroma ) ( Paz ) ( Rami… )   |   <- one-tap recent merchant chips
|                                                    |
|   Category:  ( Eating out ✕ )                       |   <- suggestion chip when one exists,
|              or  [ Choose category ]               |      else a tap target; never required
|                                                    |
|   Today · 14 Jun            [ More ▾ ]             |   <- date defaults to today; More hidden
|                                                    |
+---------------------------------------------------+
|                                                    |
|              [   Save expense   ]                  |   <- primary action, thumb-reachable
|                                                    |
|   [ 1 2 3 ]                                         |
|   [ 4 5 6 ]   numeric keypad (up on open)          |
|   [ 7 8 9 ]                                         |
|   [ . 0 ⌫ ]                                         |
+---------------------------------------------------+
```

Field order and focus:

1. Amount — first field, auto-focused on open with the numeric keypad already up. The user can type and save without touching anything else.
2. Merchant (optional) — directly below amount. Recent/frequent merchant chips sit under it for one-tap selection (§6). Typing here triggers autocomplete.
3. Category — a single suggestion chip when the merchant resolves one (one-tap confirm or clear); otherwise a compact "Choose category" target that opens the picker. Never blocks save.
4. Date — a small "Today · 14 Jun" line defaulting to today; tapping it reveals a date control. Zero interaction required in the common case.
5. Save — large, persistent, thumb-reachable primary button. Enabled the moment a valid amount exists.

Hidden behind progressive disclosure ("More ▾", never in front of the primary path):

- Optional note (free text).
- Date change control (also reachable by tapping the date line).
- "Mark as income/refund" toggle (§5) — off by default; Quick Add is for expenses.
- Any "create a rule" affordance is NOT here; it appears post-save as a soft prompt (§8), so it never adds a step to capture.

Cancel/back behavior: the dismiss control ("Cancel" / back at logical start) closes Quick Add without saving. If the user has typed an amount and tries to dismiss, show a light, non-alarming confirm only if there is unsaved input ("Discard this entry?" / "Keep editing" / "Discard"). An empty Quick Add dismisses silently. Never trap the user.

---

## 5. Amount input behavior

- Currency: ILS by default, shown as ₪ at the logical start of the amount (RTL-safe placement, §14). v0.0.1 assumes a single base currency (PRD §19); the currency code is stored on the transaction for the future but is not a per-entry choice in Quick Add.
- Decimal support: the keypad includes a decimal separator. The user may enter whole shekels ("33") or with agorot ("33.50"). Display is in major units (₪33.50); storage is signed integer minor units (3350) — conversion happens at storage, never shown to the user (firm invariant; MANUAL_FIRST_MVP_REVISION §9).
- Validation (inline, minimal): reject empty, zero, and non-numeric amounts. The Save button stays disabled until a valid positive amount exists; no error nag is shown for an empty field the user simply hasn't filled yet — the disabled Save is the signal. If the user explicitly tries to save an invalid amount, show a single calm inline hint at the field ("Enter an amount to save").
- Zero / negative: zero is not a valid expense and Save stays disabled. Negative is not entered via a minus key in the main flow; "money back" is handled by the explicit refund toggle below, not by typing a negative.
- Refund / income: NOT in the main Quick Add path. Quick Add defaults to an expense (`direction = debit`). A refund or income is entered only by explicitly toggling "Mark as income/refund" behind "More" (§4). A refund is recorded so it nets against the relevant category rather than inflating spend (CATEGORY_TAXONOMY §7). Keeping this off the happy path protects the five-second expense case, which is the overwhelming majority.
- Amount is the one truly required element. Everything else has a default or is optional. A valid amount is both necessary and sufficient to save (Mode A).
- Very large amounts: see §11 (a soft confirmation for unusually large values, never a block).

---

## 6. Merchant input behavior

Driven entirely by MERCHANT_NORMALIZATION_SPEC. Merchant is OPTIONAL.

- Recent/frequent suggestions: below the merchant field, show the user's own recent and frequent merchants as one-tap chips, ranked by recency (`last_seen_at`) and frequency (§8 of the merchant spec). Before any history exists, this row is simply absent (no placeholder clutter).
- Autocomplete while typing: as characters arrive, surface matching recent/known merchants (the `recent_suggestion` confidence level). Matching runs asynchronously and must never block amount entry or the Save button (§8 of the merchant spec).
- Auto-select on strong match: when the typed text resolves at `exact`, `alias_exact`, or `normalized_exact` (same-script, deterministic), the existing merchant is auto-selected silently and its category is pre-filled (§7 of the merchant spec). No prompt, no friction.
- Suggestions only for low confidence: `recent_suggestion` and `contains` are shown as tap-to-select suggestions; cross-script candidates (Golda / גולדה) are surfaced as a soft "Same as Golda?" suggestion. None of these auto-merge. The user's tap is the decision.
- No silent fuzzy merge: `fuzzy_possible` behaves as `none` in v0.0.1; a typo like "Goldaa" does not silently merge into "Golda" (§7, §12 of the merchant spec). It takes the create-new path unless the user picks a surfaced recent suggestion.
- Creating a new merchant from typed text: if the typed merchant matches nothing (`none`), saving creates a new merchant from the raw input (display name from what they typed). No extra confirmation step — the merchant simply starts existing and becomes available for reuse next time.
- Saving amount-only when merchant is blank: leaving the merchant field empty is fully supported and is the Mode A path — `merchant_id = null`, save proceeds. No prompt, no warning.
- Generic / transfer-like names: "Paybox", "Bit", "ATM", "Transfer" and similar are low-trust and never auto-anchor a rule (§12 of the merchant spec). The user can still type them; they just don't trigger merchant memory or rule prompts.

---

## 7. Category behavior

Driven by CATEGORY_TAXONOMY. Category is OPTIONAL but encouraged.

- Auto-suggest from merchant: when a merchant resolves, the category is pre-filled using the precedence ladder (user_correction merchant_exact > user_correction contains > system merchant_exact > system contains > recent-merchant memory > merchant default > uncategorized) (CATEGORY_TAXONOMY §9, MERCHANT_NORMALIZATION_SPEC §9). The first level that resolves wins. The suggestion appears as a single chip the user confirms (implicitly, by saving) or clears.
- One-tap override: tapping the category chip (or "Choose category") opens the picker; the user's choice always wins (PRD principle 5).
- Picker contents and order: only the 14 Layer A consumer categories (plus the option to leave it Uncategorized) appear. Layer C bank categories NEVER appear in Quick Add (CATEGORY_TAXONOMY §11). Ordering is most-used-first for this user, computed from their history; before history exists, the default lead order is Groceries, Eating out, Transport, Car / fuel, Shopping, then the rest. Recent categories appear as quick chips at the top of the picker.
- No category history for this merchant: if a known merchant has no category memory yet, show the user's most-used categories first (the same default-order list), so a choice is one tap.
- Uncategorized when unsure: leaving it uncategorized is a first-class, encouraged escape when the user expects to categorize later. It is never silently coerced into Other (CATEGORY_TAXONOMY §8).
- Other spending, used sparingly: `other_spending` is available in the picker for a genuine one-off the user wants "done." It is a controlled safety valve, not a dumping ground; repeated or large items in Other are prompted out later (CATEGORY_TAXONOMY §8), but that policy lives in review surfaces, never as friction at capture time.

---

## 8. Confirmation prompts

Firm rule across all prompts: a prompt must NEVER block the initial save. Save first, then ask softly in the success state. The user can always ignore a prompt and the transaction stays saved.

### "Always categorize this merchant as X?"

- When shown: after saving a transaction that has BOTH a merchant and a category, AND no existing trusted `merchant_exact` rule for that merchant yet (MERCHANT_NORMALIZATION_SPEC §10, CATEGORY_TAXONOMY §9).
- When NOT shown: amount-only entries (no merchant); blank-merchant transactions; one-off `other_spending` entries; when a trusted rule already exists; generic/transfer-like merchants (§6).
- Placement: in the post-save success state, as a soft, dismissible chip/row — not a modal that gates the next action.
- Options: "Yes, remember" (creates/updates a `merchant_exact` user_correction rule keyed to the merchant's normalized name, firing across its aliases) / "Not now" (changes nothing beyond this transaction; recent-merchant memory still updates).
- Microcopy: "Want me to file Golda under Eating out next time?" — neutral, not pushy.

### "Same as existing merchant?" (cross-script / alias)

- When shown: on a cross-script or possible-alias match (e.g. typed "גולדה" when "Golda" exists; or a `contains`/branch candidate like "Golda Givatayim" vs "Golda"). These never auto-merge (MERCHANT_NORMALIZATION_SPEC §5, §7, §12).
- Placement: as a soft suggestion either inline as a tappable hint while typing, or in the success state after save — never a blocking modal.
- Options: "Yes, link them" (stores a `user_confirmed` alias so future variants auto-select the merchant) / "No, keep separate" (the typed form stays its own merchant; no alias).
- Microcopy: "Is גולדה the same place as Golda?" — and the choice is permanent and correct once made.

Why save-first: the capture moment is sacred. A prompt that gates the save adds a step and a decision exactly when we need zero friction. By saving first and asking after, the transaction is never at risk, and the user can enrich at their own pace or not at all.

---

## 9. Recurring expense entry

This is a SEPARATE flow from Quick Add, reached from recurring-templates management (e.g. Settings or a "Commitments" area), not from the "+" capture button. It must not appear in or slow the expense capture path.

Fields (RecurringExpenseTemplate, MANUAL_FIRST_MVP_REVISION §7, §9):

- name (e.g. "Gym", "Car insurance", "Netflix").
- amount (signed integer minor units, ₪ default).
- category (a Layer A consumer key reused for grouping — e.g. gym → `health`, streaming → `subscriptions`, rent/phone/internet → `home`; CATEGORY_TAXONOMY §5).
- cadence (weekly / monthly / yearly; monthly is the common case).
- next_expected_date.
- optional note.
- counts_in_projection (default true) — include in the month's projected commitment; can be excluded without deleting.
- is_active (default true) — inactive templates stop projecting but stay for history.

RESTATEMENT (firm): in v0.0.1, recurring templates do NOT create actual transactions. They only contribute to the projected commitment total shown on Home as "Upcoming commitments." There is no auto-generated spend, no auto-reconciliation against a matching real transaction. This deliberately removes a whole class of double-counting/duplicate bugs (MANUAL_FIRST_MVP_REVISION §7, CATEGORY_TAXONOMY §5). The actuals (manually entered transactions) remain the single source of truth for spending.

The recurring flow can be a simple form (no five-second pressure — it is set up rarely, then forgotten). It is still RTL-safe and uses neutral copy.

---

## 10. Post-save behavior

- Quick success state: a brief, calm confirmation ("Saved ✓" / "Added ₪33"). No celebration animation that delays the next action; no judgement.
- Add another immediately: the dominant follow-up. Offer a prominent "Add another" that reopens Quick Add fresh (amount focused, keypad up) so logging several purchases is fast. (Assumption: people often log a few backlogged purchases at once.)
- Edit: offer a quick "Edit" on the just-saved entry for an immediate fix (wrong amount, wrong category) without hunting for it in a list.
- Update Home totals: "Spent so far", the relevant category total, Top category, and Recent transactions reflect the new entry immediately on return to Home.
- Gentle enrich prompts: if relevant, show the soft "Always categorize…?" and/or "Same as Golda?" prompts here (§8). They sit alongside "Add another" / "Edit" / "Done" and never block any of them.
- Do not trap the user: the success state always has a clear, single-tap exit ("Done" / dismiss). No confirmation chains, no forced rule decision, no "are you sure" on a normal save.

Success-state layout sketch:

```
+---------------------------------------------------+
|                  Saved ✓  ₪33                      |
|                                                    |
|   Want me to file Golda under Eating out next     |   <- soft, optional (§8)
|   time?      ( Yes, remember )  ( Not now )         |
|                                                    |
|   [ Add another ]   [ Edit ]            [ Done ]   |
+---------------------------------------------------+
```

---

## 11. Error and edge states

All messages are calm, specific, and useful. No shame, no scary red full-screen errors (PRD principle 8).

- Missing amount: Save stays disabled; no nag while the field is simply empty. On an explicit save attempt: inline hint "Enter an amount to save." (§5)
- Invalid amount (non-numeric / zero): inline hint at the field, "Enter an amount above ₪0." Save stays disabled.
- Very large amount: not blocked. On save of an unusually large value (assumption: above a sensible threshold, e.g. ₪10,000, or well above the user's typical entry), show a soft inline confirm "That's a big one — ₪12,000, save it?" / "Yes, save" / "Edit." Prevents fat-finger errors without judging the spend.
- Offline / backend unavailable: saving must still feel safe. (Assumption, to be confirmed by the schema/API owners: queue the entry locally and sync when back online; show a small "Saved · will sync" marker rather than an error.) If local-first is not feasible in v0.0.1, show a calm retry: "Couldn't save right now — tap to retry," and preserve the typed input so nothing is lost.
- Save failure (server error): "Couldn't save that — your entry is still here. Try again?" Keep all fields populated; never silently drop input.
- Duplicate-looking manual entry: if a near-identical entry (same amount + merchant + today) was just saved, show a soft, non-blocking note in the success/confirm step: "Looks like you just added ₪33 at Golda — add again or skip?" / "Add again" / "Skip." Never auto-block a legitimate repeat purchase (two coffees happen).
- Merchant suggestion failed (autocomplete/lookup error): degrade silently to a plain text merchant field. The user can still type and save; absence of suggestions is never an error message. (Privacy: log only an event id + result enum, never the typed text, §15.)
- Category list failed to load: fall back to the default-order list of the 14 categories (a known static set), and allow Uncategorized. If even that fails, allow save as uncategorized — capture is never blocked by a categorization read failing.

---

## 12. Home integration

Home must pass the five-second test and must NEVER blend actual spending with projected commitments without labels (MANUAL_FIRST_MVP_REVISION §10, CATEGORY_TAXONOMY §12). Quick Add feeds Home; Home must reflect Quick Add honestly.

What Home shows (manual-first v0.0.1), in order of importance, using the CATEGORY_TAXONOMY §12 labels:

1. "Spent so far" — the headline: sum of Layer A actual manual spend this month. Excludes settlements and templates by construction.
2. "Upcoming commitments" — the projected total from active templates where `counts_in_projection = true` (Layer B), as a clearly separate, clearly labelled number. A commitment, not money already spent.
3. "Known this month" — actual + projected, presented so the two parts stay VISIBLY separate (e.g. "Spent ₪2,140 · Committed ₪1,300"), never merged into one ambiguous figure.
4. Top actual category — the single largest Layer A category this month, one tap into its "Spending detail."
5. Recent transactions — the last few entries (including amount-only / uncategorized ones, clearly marked) for quick recall and correction.
6. Upcoming recurring commitments — a short forward-looking list of the next template charges due (Layer B).

```
+---------------------------------------------------+
|   June 2026                                        |
|                                                    |
|   Spent so far          ₪2,140                     |   <- headline (actual, Layer A)
|   Upcoming commitments  ₪1,300                     |   <- projection (Layer B), separate
|   Known this month   Spent ₪2,140 · Committed ₪1,300|  <- split, never blended
|                                                    |
|   Top category:  Groceries  ₪780        >          |
|                                                    |
|   Recent                                           |
|    Golda            ₪33    Eating out              |
|    (uncategorized)  ₪50    needs a category        |
|    Paz              ₪220   Car / fuel              |
|                                                    |
|                                          (  +  )   |   <- one-tap Quick Add
+---------------------------------------------------+
```

Firm rule: actual spending and projected commitments are never visually blended without labels. Blending is a correctness bug, not a styling choice. The "Cash-flow view" (Layer C) is absent in pure-manual v0.0.1 and only appears once bank import lands (v0.0.2+), always separated and with card settlements excluded from spend. No charts on Home — a number and a label beat a chart (PRD principle 3).

---

## 13. Speed rules

The five-second rule, defended concretely:

- No more than 3 visible required elements. In practice there is exactly ONE truly required element (amount). Merchant and category are optional. The screen never demands more.
- Amount first. Focused on open, keypad up. The user can type and save with no other interaction.
- Date defaults to today. Zero date interaction in the common case (MANUAL_FIRST_MVP_REVISION §6).
- Category suggestions are one tap. A resolved suggestion is confirmed implicitly by saving; overriding is one tap into the picker.
- Merchant suggestions are one tap. Recent merchant chips and autocomplete selections are single taps.
- Avoid modal chains. No sequence of "next" screens. Everything is on one screen; enrichment prompts come after save and are optional.
- Save-first, enrich-after. The Save button is enabled the instant a valid amount exists; all learning prompts happen post-save.
- The user can always save with incomplete metadata. Amount-only is a complete transaction. Incompleteness is corrected later, never forced at capture.

If any proposed addition to Quick Add would add a tap to the amount → save path, it must go behind progressive disclosure or post-save, or be rejected.

---

## 14. RTL/Hebrew readiness

First copy is English, but the layout is RTL-safe from day one so Hebrew can be added without relayout (MANUAL_FIRST_MVP_REVISION §6, CATEGORY_TAXONOMY §10).

- Logical start/end alignment everywhere; no hard-coded left/right. Labels, fields, chips, and buttons align to logical start/end so the whole screen mirrors correctly in RTL.
- Currency symbol placement: ₪ sits at the logical start of the amount and mirrors with direction; the amount's numeric value stays legible (digits are LTR even within an RTL layout; the field handles bidi correctly).
- Hebrew merchant names supported now. The merchant field accepts and displays Hebrew (שופרסל, גולדה) and mixed Hebrew/English; normalization preserves Hebrew (MERCHANT_NORMALIZATION_SPEC §4, §5). Invisible/bidi characters are stripped from the matching key but the display preserves the user's text.
- Future Hebrew labels. Every user-facing string ("Add expense", "Spent so far", "Always categorize…?") is a translatable label keyed off the stable English keys; the category Hebrew placeholders already exist (CATEGORY_TAXONOMY §10).
- Numeric input clarity in RTL. The keypad and amount display remain unambiguous in an RTL layout; the decimal separator and ₪ do not flip the number's meaning.
- Direction-neutral icons. The "+" entry point, the back/dismiss control, and the "More ▾" disclosure use icons that do not imply a wrong direction; any directional affordance (a "drill-in" chevron) mirrors with the layout.

---

## 15. Privacy and logging

Quick Add handles the most sensitive data in the app — where and how much someone spends. Privacy rules are absolute (PRD §15, MERCHANT_NORMALIZATION_SPEC §14, CATEGORY_TAXONOMY invariants).

MUST NEVER be logged:

- The typed merchant text (`raw_merchant_input`), any alias text, the normalized merchant key, or a merchant display name.
- The amount (in any unit), including per-transaction amounts.
- The note (free text — treat as highly sensitive; it may contain anything).
- Any raw typed input or any combination that re-identifies a purchase.

SAFE to log (structured, IDs / counts / enums / duration buckets only):

- Event ids (e.g. quick_add_opened, quick_add_saved), result type (success | validation_error | save_failure), and a validation error code enum (e.g. empty_amount, zero_amount).
- `merchant_confidence` LEVEL as an enum (exact | alias_exact | normalized_exact | recent_suggestion | contains | fuzzy_possible | none) — the level name only, never the text that produced it.
- Whether a category was suggested vs overridden (booleans), whether a rule prompt was shown/accepted/declined (enums) — never the category text alongside the amount/merchant.
- Counts (number of suggestions shown) and duration buckets for the save (e.g. <2s, 2–5s, >5s) to verify the five-second goal without logging content.

Notes and merchant text are sensitive by classification: notes are free text and may contain anything; merchant text reveals spending behavior (habits, health, beliefs, relationships). Both are stored in SQL, shown to the owner in-app, never logged, never embedded (raw transactions in SQL only — firm invariant). Debugging a wrong match is done by IDs and confidence-level enums, never by logging the typed text (MERCHANT_NORMALIZATION_SPEC §14).

---

## 16. Low-fidelity flow specs

Text-based wireflows. Format per flow: starting point → user actions → system response → data result → exit state.

### (1) Open Quick Add

- Starting point: Home.
- User actions: tap "+".
- System response: Quick Add opens; amount field focused; numeric keypad up; recent merchant chips loaded asynchronously (absent if no history); date shows "Today".
- Data result: none yet (no transaction created on open).
- Exit state: Quick Add ready, awaiting input.

### (2) Save amount-only (Mode A)

```
Home → (+) → [ ₪ __ ] focused
            user types "33"
            Save enabled → tap Save
            "Saved ✓ ₪33"
```

- Starting point: Quick Add open.
- User actions: type "33"; tap Save.
- System response: validates amount; saves; shows success state (Add another / Edit / Done). No rule prompt (no merchant).
- Data result: transaction { amount_minor: 3300, posted_date: today, merchant_id: null, category_id: null, source: manual }.
- Exit state: success state; "Spent so far" +₪33; entry in "needs a category" review.

### (3) Save amount + merchant (Mode B)

- Starting point: Quick Add open, amount "33" typed.
- User actions: type/tap merchant "Golda".
- System response: resolves merchant (exact/normalized auto-selects "Golda"); pre-fills category from memory if any; user taps Save.
- Data result: transaction { amount_minor: 3300, merchant_id: <Golda>, category_id: <Eating out or null>, source: manual }.
- Exit state: success state; if no trusted rule yet and a category was set, soft "Always categorize Golda as Eating out?" appears.

### (4) Save amount + merchant + category (Mode C)

- Starting point: Quick Add open, amount + merchant set, category suggested or picked.
- User actions: confirm/override category; tap Save.
- System response: saves fully categorized transaction; updates recent-merchant memory; offers rule prompt if applicable.
- Data result: transaction { amount, merchant_id, category_id (Layer A), source: manual }.
- Exit state: success state; Top category / category total updated on Home.

### (5) Select recent merchant

```
[ ₪ 33 ]
[ Merchant (optional) ]
recent:  ( Golda )  ( Aroma )  ( Paz )
            ↑ tap
→ Golda selected, category auto-fills "Eating out"
```

- Starting point: Quick Add open, amount typed.
- User actions: tap a recent merchant chip (e.g. "Golda").
- System response: merchant auto-selected (exact/alias level); category pre-filled per §9.
- Data result: merchant_id + suggested category_id staged for save.
- Exit state: ready to Save in one more tap (the two-tap-plus-amount happy path).

### (6) Override category

- Starting point: a merchant resolved with a suggested category the user disagrees with.
- User actions: tap the category chip → picker opens → pick a different Layer A category.
- System response: category replaced; user's choice wins; recent-merchant memory will update on save.
- Data result: transaction saved with the overridden category_id.
- Exit state: success state; if no trusted rule exists, soft "Always categorize…?" offered with the NEW category.

### (7) Confirm "Always categorize"

```
post-save success:
  "Want me to file Golda under Eating out next time?"
        ( Yes, remember )   ( Not now )
```

- Starting point: post-save success state (merchant + category present, no trusted rule).
- User actions: tap "Yes, remember" or "Not now."
- System response: "Yes" creates/updates a merchant_exact user_correction rule keyed to the merchant; "Not now" changes nothing further.
- Data result: CategoryRule created/updated (on Yes) keyed to merchant normalized name; fires across aliases.
- Exit state: success state remains; user proceeds to Add another / Done. Never blocked.

### (8) Confirm "Same as existing merchant"

```
typing "גולדה" (Golda exists):
  hint: "Is גולדה the same place as Golda?"
        ( Yes, link them )   ( No, keep separate )
```

- Starting point: cross-script/branch candidate detected (inline while typing, or post-save).
- User actions: tap "Yes, link them" or "No, keep separate."
- System response: "Yes" stores a user_confirmed alias so future variants auto-select the merchant; "No" keeps the typed form as its own merchant.
- Data result: MerchantAlias (user_confirmed) created on Yes; nothing on No.
- Exit state: save unaffected; merchant identity resolved per the user's choice; permanent and correct thereafter.

### (9) Create recurring commitment

- Starting point: Commitments / recurring management (NOT the "+" capture button).
- User actions: tap "Add commitment"; fill name, amount, category, cadence, next date; optional note; leave counts_in_projection on; save.
- System response: creates a RecurringExpenseTemplate; updates the projection total.
- Data result: template row; NO actual transaction created (firm).
- Exit state: template listed; "Upcoming commitments" on Home reflects the new projection.

### (10) Edit a saved transaction

- Starting point: Recent transactions on Home, or a category/transaction detail.
- User actions: tap an entry → edit amount / merchant / category / date / note → save.
- System response: updates the transaction; if the category changed for a merchant without a trusted rule, offer "Always categorize…?"; recalculates Home totals.
- Data result: transaction fields updated; optional CategoryRule on confirmation.
- Exit state: updated entry; Home totals and category rankings reflect the change.

---

## 17. Acceptance criteria

This spec is complete when ALL hold:

1. The user can save an amount-only transaction (amount + today's date, merchant_id=null, category_id=null) as a first-class path.
2. The user can save a fully categorized transaction (amount + merchant + category) in under five seconds via the amount → tap merchant → save happy path.
3. Merchant is optional and never blocks save; recent/frequent merchant suggestions are defined (§6, §16-5).
4. Category is optional and never blocks save; category auto-suggestion via the precedence ladder is defined; only the 14 Layer A categories (plus uncategorized) appear; Layer C never appears (§7).
5. Confirmation prompts ("Always categorize…?", "Same as Golda?") are save-first, soft, and never block capture or trap the user (§8).
6. Recurring commitments are a separate flow that creates NO actual transactions and contributes only to the projection (§9).
7. Home shows "Spent so far", "Upcoming commitments", and "Known this month" with actual and projected always visibly separated, plus Top category and Recent transactions (§12).
8. The flow is RTL-safe (logical start/end, Hebrew merchant input supported, direction-neutral icons) even though first copy is English (§14).
9. Privacy holds: merchant text, amounts, notes, and raw input are never logged; only IDs/counts/enums/duration buckets are (§15).
10. The next DB schema and API contract can support this UX without immediate revision — nullable merchant_id and category_id, signed minor units, default-today date, recurring templates as projection-only, and the save-first prompt model are all consistent with the upstream entity shapes (MANUAL_FIRST_MVP_REVISION §9, MERCHANT_NORMALIZATION_SPEC §13).

---

## 18. Next recommended prompt

Firm recommendation: proceed to docs/DATABASE_SCHEMA_V0_0_1.md next.

Justification: the document chain (CATEGORY_TAXONOMY §15 → MERCHANT_NORMALIZATION_SPEC §18 → this spec) has now pinned down the three things that were blocking a safe schema: the taxonomy (seed categories), the merchant-matching logic (Merchant / MerchantAlias / CategoryRule shapes), and — with this document — the interaction model (nullable merchant_id and category_id, default-today dates, amount-only as first-class, recurring templates as projection-only, save-first prompts that promote memory to rules). The schema can now be written against a settled UX rather than a guessed one, which is exactly the sequencing the upstream docs insisted on (MERCHANT_NORMALIZATION_SPEC §18: "do QUICK_ADD_UX_SPEC first… then DATABASE_SCHEMA_V0_0_1 immediately after").

I considered recommending API_CONTRACT_V0_0_1.md first and reject it, deliberately: the API contract should be shaped by the persisted data model, not the reverse. Writing the contract before the schema risks endpoints that assume a merchant/category/transaction shape the schema then revises (the same trap the earlier docs warn about). The schema is also the lower-risk, more foundational artifact — it unblocks backend and database work, seeds the 14 categories and the Layer C cash-flow categories, and encodes the firm invariants (signed minor units, UTC metadata, user_id everywhere, nullable import fields, unique(user_id, dedup_hash) for imported rows). The API contract is the correct step immediately AFTER the schema, written against frozen entities.

Exact next prompt to send after approving this spec:

> "Acting as the database-engineer agent with the product-architect and backend-api-engineer agents, and using docs/PRD_V0_1.md as the long-term vision, docs/MANUAL_FIRST_MVP_REVISION.md as the governing v0.0.1 decision (especially §9 data model impact), docs/CATEGORY_TAXONOMY.md as the finalized taxonomy (§10 seed table), docs/MERCHANT_NORMALIZATION_SPEC.md as the merchant-matching logic (§13 data model implications), and docs/QUICK_ADD_UX_SPEC.md as the settled interaction model, produce docs/DATABASE_SCHEMA_V0_0_1.md for manual-first v0.0.1. Define the concrete schema for User, Transaction (with nullable merchant_id/category_id, source, nullable import fields, is_card_settlement default false, dedup_hash nullable for manual and unique(user_id, dedup_hash) for imported), Merchant, MerchantAlias (first-class rows with source/confidence/timestamps), Category (seed the 14 Layer A consumer categories plus the 8 Layer C bank-movement categories from the taxonomy §10 table, is_system, user_id null for system), CategoryRule (match_type, match_value, category_id, priority, source), and RecurringExpenseTemplate (projection-only, counts_in_projection, is_active, cadence, next_expected_date). Mark Account and ImportBatch as retained-but-deferred-for-active-use. Honor every firm invariant: signed integer minor units + ILS default, UTC for metadata timestamps, financial dates date-only, user_id on every user-owned row, raw transactions in SQL only and never embedded, no PII in logs. Provide seed data for the categories and the indexes the Quick Add flow needs (recent-merchant lookup, normalized-name and alias-key lookups, per-user/per-month transaction queries). Planning and specification only, no migration files, no code."

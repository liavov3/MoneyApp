# Money App — Mobile UI/UX Spec (v0.0.1)

Status: **UI/UX specification only.** No frontend code, no backend changes, no
endpoints, no migrations. Every screen maps to an EXISTING backend capability;
anything not yet supported is marked **[Backend follow-up]** and never drawn as
if it already works (contract-guard rule). Target: Expo / React Native, later.

Authoritative backend surface used here (verified against code + frozen docs):

| Capability | Endpoint | Status |
|---|---|---|
| Dashboard | `GET /api/v1/home?month=YYYY-MM` | **live** |
| Categories (incl. `label_he`) | `GET /api/v1/categories` | **live** |
| Quick Add (returns `category_suggestion`) | `POST /api/v1/transactions/quick-add` | **live** |
| List transactions | `GET /api/v1/transactions` (month/category/uncategorized, keyset cursor) | **live** |
| Read one | `GET /api/v1/transactions/{id}` | **live** |
| Full edit | `PATCH /api/v1/transactions/{id}` (amount/type/date/note/category) | **live** |
| Categorize (+rule promotion) | `POST /api/v1/transactions/{id}/categorize` | **live** |
| Delete | `DELETE /api/v1/transactions/{id}` | **live** |
| Recent merchants | `GET /api/v1/merchants/recent` | **live** |
| Merchant autocomplete | `GET /api/v1/merchants/suggestions?query=` | **live** |
| Fixed-expense **display** on Home (`committed_amount_minor`, `upcoming_commitments`, `known_this_month`) | `GET /api/v1/home` | **live** |
| Fixed-expense **CRUD** | `GET/POST/PATCH/DELETE /api/v1/recurring-templates` | **[Backend follow-up]** — frozen in API_CONTRACT §12, not yet implemented |
| Email/password auth | — | **[Backend follow-up]** — only a dev bearer token exists today |
| Previous-month comparison | (no field) | **No gap** — fetch `GET /home?month=<prev>` and compare `spent_so_far_minor` |

---

## 1. Product UX principles

1. **Manual-first.** The app's job is to make logging a purchase faster than the
   user's resistance to logging it. Everything else serves that.
2. **Fast expense entry.** Amount is the only required field; a valid amount is
   one tap from saved (Quick Add Option C).
3. **Clear monthly overview.** Home answers "how much this month, on what" in
   five seconds — numbers and labels, not charts.
4. **Quiet smart suggestions.** Suggestions appear as a single calm chip
   ("קטגוריה מוצעת"); the user confirms by tapping. Never expose rules / memory /
   merchant-default internals.
5. **Planned vs actual, always separated.** Actual spend (transactions) and
   planned commitments (הוצאות קבועות) are different sections with different
   labels and never summed into one number.
6. **Professional, non-judgmental tone.** No "you overspent", no emoji scores,
   no gamification.
7. **Hebrew-first, RTL-first.** Every screen is authored RTL; logical
   start/end, never hard-coded left/right.

---

## 2. Information architecture

Primary areas (kept deliberately small):

- **Home** (בית) — monthly overview, the default screen.
- **Quick Add** (הוספת הוצאה) — a modal sheet, reachable from everywhere.
- **Transactions** (עסקאות) — the month's list, drill-in to edit.
- **Transaction Details / Edit** — pushed from the list (not a tab).
- **Category Picker** — a sheet invoked from Quick Add / Edit / suggestion.
- **Fixed Expenses** (הוצאות קבועות) — list + add/edit of recurring templates.
- **Settings / Profile** — pushed from the Home header (not a tab).

---

## 3. Navigation model

**Recommended (MVP): bottom tab bar with 3 tabs + a prominent center Add FAB.**

```
RTL order (right → left):   [ בית ]   [ ➕ ]   [ עסקאות ]   [ הוצאות קבועות ]
                              Home    Quick    Transactions   Fixed Expenses
                                      Add(FAB)
```

- The **Add** action is the visually dominant control: a raised, accent-filled
  circular FAB seated in the center of the tab bar. Tapping it opens the Quick
  Add sheet over any tab.
- **Settings** is a gear icon in the Home header — not worth a tab in a
  single-user MVP.
- Transaction Details/Edit, Category Picker, Add/Edit Fixed Expense are
  **pushed screens / sheets**, not tabs.

Why this over alternatives: 3 tabs cover the three things the user returns to
(overview, history, commitments); the FAB keeps the core loop one tap away from
anywhere. A drawer or 5-tab bar adds chrome without adding loop value.

> ponytail: if Fixed Expenses proves low-traffic, drop it to a Home section +
> "ניהול" link and go to 2 tabs. Start at 3; cut later, don't add later.

---

## 4. Screen-by-screen UX

Conventions for every screen: **Empty / Loading / Error** states are mandatory;
loading uses skeletons (no spinners on content areas); errors use a calm inline
banner with retry, never a raw message (backend returns generic envelopes).

### A. Login / user gate
- **Goal:** get an authenticated principal before showing data.
- **MVP reality:** backend has only a dev bearer token, no email/password.
- **MVP screen:** a minimal gate that holds/injects the token (config/secure
  storage) and routes to Home. No signup, no onboarding carousel.
- **Actions:** "המשך" (continue) once a token is present.
- **Empty/Loading/Error:** Loading = brief splash while validating; Error =
  "אין חיבור לחשבון" with retry.
- **APIs:** any authed call (e.g. `GET /home`) validates the token.
- **[Backend follow-up]:** real email/password (or OAuth) auth + multi-user. UI
  is built so a real login form drops in without restructuring.

### B. Home Dashboard
- **Goal:** the five-second monthly overview + one-tap add.
- **Actions:** tap Add (FAB); tap a category row → filtered Transactions; tap a
  recent transaction → Details/Edit; tap month label → switch month; gear →
  Settings.
- **Sections (top → bottom), each a card:**
  1. **הוצאות החודש** — `spent_so_far_minor` (actual). The headline number.
  2. **לעומת חודש קודם** — delta vs previous month's `spent_so_far_minor`
     (second `GET /home?month=<prev>` call). Neutral phrasing, e.g.
     "₪320 יותר מהחודש שעבר" / "₪150 פחות". No red/green moralizing — a small
     muted up/down indicator only.
  3. **קטגוריה מובילה** — `top_category` (label_he + total). Hidden if null.
  4. **לפי קטגוריות** — `category_totals` as labelled rows with a proportion
     bar. No pie chart.
  5. **הוצאות קבועות** — planned: `committed_amount_minor`
     (= `known_this_month.committed_projected_minor`). Clearly labelled
     "מתוכנן", visually distinct (different card tint), never added to §1.
  6. **חיובים קרובים** — `upcoming_commitments` (amount + `next_expected_date`;
     name shown only via the Fixed Expenses list since Home payload sends
     `name_present` only — show category + date here).
  7. **עסקאות אחרונות** — `recent_transactions` (last few, uncategorized rows
     flagged calmly).
- **Empty:** no transactions → headline "₪0", "עדיין לא נרשמו הוצאות החודש",
  big Add nudge; category/recent cards collapsed.
- **Loading:** skeleton cards.
- **Error:** inline banner + "נסה שוב".
- **APIs:** `GET /home` (current month) + optional `GET /home?month=<prev>` for
  the comparison. `GET /home` already separates actual vs planned — no blending.
- **Follow-ups:** none required; planned/actual separation and commitments are
  live. (A single combined "prev vs current" field is a possible future
  convenience, not needed.)

### C. Quick Add (sheet)
- **Goal:** save an expense in 2–3 taps. Amount-only is valid.
- **Layout (RTL):** amount field focused on open, numeric keypad up; below it,
  optional merchant field with recent chips; optional category chip row; date
  defaults to "היום"; optional note; "שמור" enabled the instant a valid amount
  exists.
- **Actions:**
  - Type amount → "שמור" (amount-only save is allowed).
  - Type merchant → autocomplete suggestions appear quietly
    (`merchants/suggestions`); tapping a recent chip fills the merchant text.
  - Optionally pick a category (Category Picker sheet).
  - Save → success toast; if response has `category_suggestion`, show the quiet
    suggestion (screen D).
- **Empty:** recent-merchant chip row simply absent before any history (no
  placeholder clutter).
- **Loading:** "שומר…" on the button; suggestions load async and never block
  Save.
- **Error:** field-level validation from the backend envelope
  (`zero_amount` → "סכום לא תקין", `too_many_decimals` → "עד שתי ספרות אחרי
  הנקודה", `invalid_date` → "תאריך לא תקין"). Nothing persists on error.
- **APIs:** `POST /transactions/quick-add` (sends `amount`, optional
  `merchant_input` text, `category_id`, `occurred_on`, `note`);
  `GET /merchants/recent`; `GET /merchants/suggestions?query=`.
- **Follow-ups:** none. (The pre-resolved `merchant_id` chip path is deferred in
  the backend, but tapping a chip to fill `merchant_input` text works today.)

### D. Category Suggestion confirmation (post-save, quiet)
- **Goal:** let the user accept the suggested category in one tap, without
  exposing how it was derived.
- **Trigger:** Quick Add response includes `category_suggestion` (the saved row
  is intentionally NOT auto-categorized — suggest-only).
- **UI:** a slim inline banner / bottom chip after the success toast:
  > קטגוריה מוצעת: **אוכל בחוץ**   [אישור]  [בחירת קטגוריה אחרת]
- **Actions:**
  - **אישור** → `POST /transactions/{id}/categorize` with the suggested
    `category_id` (no rule promotion in this quiet path — `promote_to_rule`
    stays false).
  - **בחירת קטגוריה אחרת** → Category Picker → `categorize` with the chosen id.
  - **Dismiss** (swipe / "אחר כך") → nothing happens; the row stays
    uncategorized and surfaces in the uncategorized review later.
- **Never shown:** the words rule / memory / default, or any reason text.
- **APIs:** `POST /transactions/{id}/categorize`.

### E. Category Picker (sheet)
- **Goal:** pick one consumer category fast.
- **UI:** a **scrollable grid of chips** (icon + Hebrew label), ~3 columns,
  selected chip filled with the accent. Grid beats a long list for ~14 items and
  reads well RTL.
- **Source:** `GET /categories`, filtered client-side to
  `layer == consumer_spending` (the 14). Labels from `label_he`. Bank-movement
  categories never appear (backend also rejects them with
  `not_consumer_category`).
- **Empty/Loading/Error:** categories are seeded + cacheable, so this is
  effectively always populated; show skeleton chips on first load.
- **Search:** **not MVP** (14 items fit on a couple of scrolls).
- **APIs:** `GET /categories` (cache for the session).

### F. Transactions List
- **Goal:** review and correct the month's entries.
- **UI:** month header (switchable); a flat list of transaction rows
  (merchant/category label, date, amount). Uncategorized rows show a calm
  "ללא קטגוריה" tag — not a red alert.
- **Actions:** tap a row → Details/Edit; scroll → keyset pagination
  (`next_cursor`); switch month; optional filter to uncategorized.
- **Empty:** "אין עסקאות בחודש זה" + Add nudge.
- **Loading:** skeleton rows.
- **Error:** inline banner + retry.
- **APIs:** `GET /transactions?month=YYYY-MM` (+ `uncategorized=true`,
  `category_id=`, `cursor=`).
- **Search/full-text:** **not MVP** (filters cover the need).

### G. Transaction Details / Edit
- **Goal:** view one transaction and correct anything.
- **Full edit IS supported** (`PATCH /transactions/{id}` covers amount,
  transaction_type, occurred_on, note, category_id; `category_id:null` clears).
- **UI / editable fields:**
  - Amount — editable (re-validated; sign owned by server via type).
  - Type (expense/income/refund) — editable.
  - Category — editable (opens Category Picker; consumer-layer only).
  - Date — editable (date picker; no future-date beyond ~1 day).
  - Note — editable.
  - **Merchant — view today; editing is [Backend follow-up].** PATCH's
    `merchant_*` path is deferred (ignored by the API). Show the current
    merchant read-only with an "עריכת בית עסק (בקרוב)" affordance, disabled.
  - Delete — destructive, with confirm.
- **Actions:** edit a field → "שמירה"; or delete.
- **Destructive confirm:** dialog "למחוק את העסקה? פעולה זו אינה הפיכה" →
  [מחיקה] [ביטול]. On confirm: `DELETE` → 204 → back to list.
- **Empty/Loading/Error:** Loading skeleton; a missing/non-owned id returns 404
  → "העסקה לא נמצאה" and pop back.
- **APIs:** `GET /transactions/{id}`, `PATCH /transactions/{id}`,
  `POST /transactions/{id}/categorize` (when only changing category),
  `DELETE /transactions/{id}`.
- **[Backend follow-up]:** merchant edit via PATCH (currently deferred).

### H. Fixed Expenses / הוצאות קבועות (list)
- **Goal:** manage planned monthly commitments — clearly NOT spending.
- **UI:** a list of fixed-expense rows: name, category (label_he), amount,
  "חיוב הבא: <date>", active/inactive state. A header total "סה""כ הוצאות
  קבועות: ₪X" (magnitude). An "הוספה" button.
- **Framing:** copy and visuals say *planned* ("מתוכנן", "צפוי"), never "שולם".
  These rows are never drawn as transactions.
- **Actions:** tap → Add/Edit (screen I); add new; deactivate / delete.
- **Empty:** "לא הוגדרו הוצאות קבועות" + short explainer + "הוספה".
- **Loading/Error:** skeleton rows / inline banner.
- **APIs:** `GET /recurring-templates?active=`  **[Backend follow-up — not yet
  implemented]**. Until it ships, Home's "הוצאות קבועות" / "חיובים קרובים"
  sections (from `GET /home`) are the read-only view that DOES work; the full
  management list needs §12 implemented.
- **Note:** the *display* on Home is live; the *CRUD management screen* is the
  gated part.

### I. Add / Edit Fixed Expense
- **Goal:** define one recurring commitment.
- **Fields (map to `recurring_expense_templates`):**
  - שם (name) — required.
  - סכום (amount) — required; positive major units (server stores signed,
    projects by magnitude).
  - קטגוריה (category_id) — required; consumer-layer only.
  - בית עסק (merchant) — optional.
  - תדירות (cadence) — **MVP: monthly only** (display "חודשי"). Weekly/yearly
    are accepted by the schema but kept out of the MVP UI (mark "בקרוב").
  - יום בחודש / תאריך חיוב הבא (`next_expected_date`) — MVP collects a
    **day-of-month (1–31)**; clamp to month length per
    `RECURRING_COMMITMENTS_SPEC §6` (e.g. 31 → Feb 28/29). Stored as a concrete
    `next_expected_date`.
  - הערה (note) — optional.
  - פעיל/לא פעיל (is_active) — toggle.
- **Actions:** "שמירה"; on Edit also "השבתה" (deactivate, primary stop) and
  "מחיקה" (destructive, confirm).
- **Validation/Errors:** `not_consumer_category`, `zero_amount`,
  `negative_amount`, invalid day → calm field errors.
- **APIs:** `POST/PATCH/DELETE /recurring-templates`  **[Backend follow-up — not
  yet implemented]**.
- **Important:** creating/editing here writes **zero** transactions (projection
  only).

### J. Settings / Profile
- **Goal:** identity + sign-out + version. Nothing more.
- **UI:** user identity if available; "התנתקות" (if/when auth supports it);
  "גרסה X.Y.Z".
- **APIs:** none required in MVP (identity from the auth context).
- **[Backend follow-up]:** real logout depends on real auth. No "export /
  delete account" in MVP.

---

## 5. Component system

Reusable, boring, composable:

- **AppShell** — RTL provider, theme, tab bar + FAB host, safe-area.
- **Header** — title + optional back/gear; RTL-aware.
- **DashboardCard** — titled container; variant `actual` vs `planned` (tint).
- **AmountDisplay** — formats agorot→₪ (RTL-safe, no float math on display).
- **CategoryRow** — icon + label_he + amount + proportion bar.
- **TransactionRow** — merchant/category, date, amount, optional "ללא קטגוריה".
- **FixedExpenseRow** — name, category, amount, next-date, active state.
- **QuickAddSheet** — amount-first form + merchant/category/date/note.
- **CategoryChip / CategoryGrid** — selectable chip; grid layout.
- **SuggestionBanner** — the quiet "קטגוריה מוצעת" inline banner.
- **EmptyState** — icon + line + optional action.
- **ErrorBanner** — calm inline error + retry.
- **Skeleton** — card/row placeholders.
- **Button** — `primary` / `secondary` / `destructive` variants.
- **ConfirmDialog** — destructive confirmation.
- **TabBarWithFab** — 3 tabs + center Add FAB.

> ponytail: one `Button` with variants, not three button components. One
> `DashboardCard` with a tint prop, not separate Actual/Planned cards.

---

## 6. Visual direction (dark premium, restrained)

- **Palette (dark):**
  - Background `#0E1116`, surface/card `#171B22`, elevated `#1E232C`.
  - Text primary `#F2F4F7`, secondary `#9AA4B2`, muted `#6B7480`.
  - Accent (single) `#4F8CFF` (calm blue) for primary actions, FAB, selected
    chips.
  - Planned/commitments tint: a desaturated violet-grey `#2A2740` card to read
    as "different from spend" without alarm.
  - Semantic: down/less `#3FB37F` muted, up/more `#E0A458` muted — used only as
    small indicators, never large red blocks (non-judgmental).
- **Cards:** radius **16**, padding 16, 1px hairline border `#222833`, subtle
  elevation (soft shadow, low opacity) — no neon, no glassmorphism.
- **Typography:** Hebrew-capable family (e.g. system + a Hebrew font like
  Heebo/Assistant later). Scale: Display 28/Heading 22/Title 17/Body 15/
  Caption 13. Numbers tabular.
- **Spacing:** 4-pt base; common 8/12/16/24.
- **Radius:** 16 cards, 12 inputs, 999 chips/FAB.
- **Category colors:** a fixed muted palette mapped by category `key`
  (deterministic), used as small dots/icon backgrounds only — not full-bleed.
- **Accessibility:** body text ≥ 4.5:1 on its surface; tap targets ≥ 44pt;
  never color-only meaning (pair the up/down indicator with text).
- **Motion:** sheet slide-in + simple fades only. No heavy/animated charts.

---

## 7. Hebrew copy (professional, clear, non-judgmental)

**Titles:** בית · הוספת הוצאה · עסקאות · פרטי עסקה · הוצאות קבועות · הגדרות
**Home sections:** הוצאות החודש · לעומת חודש קודם · קטגוריה מובילה · לפי קטגוריות
· הוצאות קבועות · חיובים קרובים · עסקאות אחרונות
**Buttons:** שמור · שמירה · אישור · ביטול · מחיקה · בחירת קטגוריה אחרת · הוספה ·
השבתה · נסה שוב · המשך · התנתקות
**Quick Add:** סכום · בית עסק (לא חובה) · קטגוריה (לא חובה) · הערה · היום
**Suggestion:** קטגוריה מוצעת: {קטגוריה}
**Empty states:**
- Home: עדיין לא נרשמו הוצאות החודש
- Transactions: אין עסקאות בחודש זה
- Fixed expenses: לא הוגדרו הוצאות קבועות
- Category top: אין מספיק נתונים להצגת קטגוריה מובילה
**Loading:** טוען… · שומר…
**Errors:** משהו השתבש, נסה שוב · אין חיבור לשרת · סכום לא תקין · עד שתי ספרות
אחרי הנקודה · תאריך לא תקין · יש לבחור קטגוריית הוצאה · העסקה לא נמצאה
**Fixed-expense labels:** חיוב הבא · תדירות · חודשי · מתוכנן · פעיל · לא פעיל ·
סה""כ הוצאות קבועות
**Transaction labels:** ללא קטגוריה · עריכת בית עסק (בקרוב)
**Destructive confirm:** למחוק את העסקה? פעולה זו אינה הפיכה

> Tone check: no "חרגת", no "בזבזת", no scores. State facts ("₪320 יותר מהחודש
> שעבר"), let the user judge.

---

## 8. API mapping summary

| Screen | APIs (existing only) | Gap |
|---|---|---|
| A Login | (token-authed call) | real auth **[follow-up]** |
| B Home | `GET /home`, `GET /home?month=<prev>` | none |
| C Quick Add | `POST /transactions/quick-add`, `GET /merchants/recent`, `GET /merchants/suggestions` | none |
| D Suggestion | `POST /transactions/{id}/categorize` | none |
| E Category Picker | `GET /categories` (filter consumer) | none |
| F Transactions | `GET /transactions` (filters + cursor) | none |
| G Details/Edit | `GET/PATCH/DELETE /transactions/{id}`, `POST …/categorize` | merchant edit **[follow-up]** |
| H Fixed list | `GET /recurring-templates` | **[follow-up: not implemented]** (Home display works) |
| I Add/Edit fixed | `POST/PATCH/DELETE /recurring-templates` | **[follow-up: not implemented]** |
| J Settings | — | logout depends on auth **[follow-up]** |

No invented endpoints. Prev-month comparison uses the existing `month` param.

---

## 9. MVP vs later

**MVP (ship with the live backend):** Home (incl. planned/actual sections +
prev-month via 2nd call), Quick Add (amount-only + suggestions), quiet category
suggestion, Category Picker, Transactions list, Transaction view/edit
(amount/type/date/note/category)/delete, minimal Settings, minimal token gate.

**MVP — gated on backend follow-up (design now, enable when shipped):** Fixed
Expenses management (list/add/edit/deactivate via `/recurring-templates` §12);
merchant editing on a transaction; real email/password auth + multi-user.

**Later:** budgets, bank import, Apple Pay capture, AI coach, push reminders,
recurring auto-detection, "mark recurring as paid", shared household, advanced
analytics/charts, export/delete account, full onboarding, weekly/yearly cadence
UI, merchant-suggestion management.

---

## 10. UI acceptance criteria

1. From any tab, the user reaches a savable Quick Add in **one tap** (FAB).
2. A valid amount alone saves an expense (Option C); merchant/category/date/note
   are optional.
3. Home shows current-month **actual** spending (`spent_so_far_minor`) as the
   headline.
4. Home shows top category and a category breakdown (`top_category`,
   `category_totals`); hidden/empty states when there's no data.
5. Home shows **recent transactions**.
6. Home shows **fixed expenses / חיובים קרובים** in a section that is visually
   and numerically separate from actual spend (never blended).
7. Previous-month comparison renders from a second `GET /home?month=<prev>`.
8. After save, if `category_suggestion` is present, a quiet "קטגוריה מוצעת"
   banner offers אישור / בחירת קטגוריה אחרת — with no rule/memory wording.
9. The user can correct a transaction's category (`categorize`) and fully edit
   amount/type/date/note (`PATCH`), and delete with confirmation.
10. Category Picker shows only the 14 consumer categories, in Hebrew.
11. The user can add/edit/deactivate a fixed expense **once `/recurring-templates`
    is implemented**; until then the screens are present but clearly gated, and
    no fixed-expense write is faked as succeeding.
12. Every screen renders correctly **RTL** in Hebrew.
13. Every data screen has **empty, loading, and error** states.
14. **No unsupported backend behavior is mocked as real** — gaps are visibly
    disabled/labelled, not silently faked.

---

## 11. Ponytail review — simplifications made

- **3 tabs + FAB**, not 5 tabs / no drawer. Settings is a header icon, not a tab.
- **Prev-month comparison reuses the `month` param** (2nd `/home` call) instead
  of requesting a new backend field.
- **Category Picker = chip grid, no search** for 14 items.
- **No charts** anywhere (pie/line) — labelled numbers + a simple proportion
  bar. Matches "no charts on Home" product rule.
- **One Button (variants), one DashboardCard (tint)** — no per-purpose
  component sprawl.
- **No onboarding, no branding work, no gamification, no analytics screen.**
- **Login is a token gate**, not a full auth UI, until backend auth exists.
- **Merchant edit deferred** to match the backend (shown read-only, not faked).
- Cut candidate flagged: if Fixed Expenses is low-traffic, collapse it into a
  Home section + manage link and drop to 2 tabs.

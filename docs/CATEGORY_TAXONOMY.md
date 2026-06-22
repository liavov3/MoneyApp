# Money App — Category Taxonomy (v0.0.1, manual-first)

Status: Planning / specification only. No code, no DB migrations, no UI. This document defines the canonical default category taxonomy that the v0.0.1 schema will seed and that Quick Add will use.
Owner: fintech-researcher (lead), with product-architect.
Governing decision: docs/MANUAL_FIRST_MVP_REVISION.md (2026-06-14) supersedes the import-first v0.0.1 scope in docs/MVP_EXECUTION_ALIGNMENT.md.
Inputs (all read): docs/PRD_V0_1.md, docs/MVP_EXECUTION_ALIGNMENT.md, docs/MANUAL_FIRST_MVP_REVISION.md, docs/IMPORT_PIPELINE_SPEC.md (especially section 13 bank cash-flow categories and section 14 card-settlement exclusion).
Firm invariants carried forward unchanged: signed integer minor units + currency code; UTC for metadata timestamps only (financial dates are date-only); user_id on every user-owned row; raw transactions in SQL only and never embedded; the `is_card_settlement` exclusion flag (IMPORT_PIPELINE_SPEC section 14) keeps bank settlements out of consumer-spending totals.
Date: 2026-06-14

Confirmed facts in this document are drawn from the four source-of-truth docs above. Anything labelled "assumption" is a product judgement by the author, not an established fact.

---

## 1. Purpose

This taxonomy exists so that the founder (the sole v0.0.1 user) can, in under five seconds, log a purchase against a small, trustworthy set of categories, and at any time see where their money actually went this month. It is the prerequisite that both the database schema (category seed data) and Quick Add (the picker plus merchant-to-category memory) depend on, so it must be settled before either is built (MANUAL_FIRST_MVP_REVISION section 14).

The manual-first pivot changes WHICH layer is primary, and that change is the whole point of this document:

- v0.0.1 uses manually entered expenses as the main source of consumer-spending truth. When the user types an actual purchase, they enter the real category at the moment of spending. This is what makes the consumer taxonomy live on day one — something import-first could not do, because a bank statement only shows aggregate monthly card settlements, not the individual purchases (MANUAL_FIRST_MVP_REVISION sections 4 and 8).
- Recurring expense templates represent PROJECTED COMMITMENTS, not actual spending. A template (gym, insurance, phone, streaming) projects a future charge; it does NOT auto-create a transaction in v0.0.1. Until an actual transaction exists, the amount is a commitment, never spend (MANUAL_FIRST_MVP_REVISION section 7).
- Bank statement imports, when added in v0.0.2+, are cash-flow support, not full consumer-spending detail. They answer "what moved through my account" (income, transfers, card settlements, fees), not "what did I spend on." Card settlements are excluded from spend by the `is_card_settlement` flag so the bank's lump payment never double-counts the manual purchases (MANUAL_FIRST_MVP_REVISION section 8; IMPORT_PIPELINE_SPEC section 14).

The taxonomy therefore has to do one hard thing well: keep three different kinds of money-meaning (actual spending, projected commitment, bank movement) cleanly separated so totals are correct and the user is never misled.

---

## 2. Taxonomy design principles

1. Small and understandable. A short list the user can hold in their head. Fourteen consumer categories (section 4) is the deliberate ceiling for v0.0.1; growth must be justified, not reflexive.
2. Fast to choose during Quick Add. Categories must be pickable in one tap, and for repeat merchants auto-suggested so the user picks nothing at all (MANUAL_FIRST_MVP_REVISION section 6).
3. Stable enough for analytics. Internal keys never change once seeded; month-over-month totals depend on category identity staying constant.
4. User-correctable. Any category is editable; a correction can create/update a CategoryRule so the same merchant is right next time (section 9). Uncategorized is a first-class state, never a fake "Other."
5. No shame or guilt language. Labels are neutral and descriptive ("Eating out", not "Wasted on takeout"). Tone is coaching, never scolding (PRD principle 8).
6. Separate actual spending from projected commitments. Layer A (spend) and Layer B (commitment) must never be summed into one ambiguous number without a label (section 12).
7. Separate consumer spending from bank cash-flow movement. Layer A (what you bought) and Layer C (what moved through the account) are different questions with different categories. They are never blended.
8. Avoid double-counting. The single most important correctness rule. A manual purchase and the bank's later card settlement for the same money must not both count as spend. The `is_card_settlement` flag enforces this (section 7, section 13).
9. Keep "Other" controlled and reviewable. "Other spending" is a temporary safety valve, never an analytics home. Repeated or large items must be prompted out of it (section 8).
10. Support future Hebrew labels and RTL. Internal keys stay English snake_case; every category carries a Hebrew display-label placeholder now so translation is additive, not a refactor. Layout assumptions stay RTL-safe (MANUAL_FIRST_MVP_REVISION section 6).

---

## 3. Three-layer model

Money in this app carries three different meanings, and a category only makes sense inside one of them. Mixing them is a correctness bug, not a style choice.

Layer A — Consumer spending categories.
- What it is: actual money the user spent on something, with a real category chosen at the moment of purchase. In v0.0.1 these come from manual Quick Add; in the future they will also come from itemized credit-card imports (the per-card export, v0.0.3).
- Role: the PRIMARY v0.0.1 categories. These power "Spent so far", top-category, and category rankings on Home.
- Counted in: actual spending totals and category analytics.

Layer B — Recurring commitment categories.
- What it is: predictable future obligations the user knows about (gym, insurance, phone, streaming, rent). A recurring template projects a charge.
- Reuse: a template MAY reuse the same category key as a consumer-spending category (e.g. a gym template uses `health`; a streaming template uses `subscriptions`). The category key is shared; the MEANING is not. A template's amount is a projected commitment until an actual transaction exists.
- Role: powers "Upcoming commitments" on Home. Never counted as spend.
- Counted in: the committed-projection total only — NOT actual spending.

Layer C — Bank movement / cash-flow categories.
- What it is: account-ledger movements from a bank statement import (income, incoming/outgoing transfers, credit-card settlement, loan payment, interest/fee, cash deposit/withdrawal). These explain money in/out, not the underlying purchase.
- Role: secondary, import-only (v0.0.2+). Powers a separate cash-flow view, never the consumer-spend view.
- Counted in: the cash-flow view. Most are excluded from consumer-spending totals; card settlements are explicitly excluded via `is_card_settlement`.

Why the separation is mandatory.
- Double-counting prevention. The clearest failure: the user manually logs "Golda 33" (Layer A spend), and a month later a bank import lands the lump credit-card settlement that already includes that 33 (Layer C). If both counted as spend, the 33 is counted twice. Keeping Layer C distinct and flagging settlements with `is_card_settlement` makes this safe by construction (IMPORT_PIPELINE_SPEC section 14).
- Honesty of totals. A projected commitment (Layer B) is money not yet moved. Counting it as spend would tell the user they spent money they have not spent. Keeping Layer B separate keeps "Spent so far" truthful.
- Different questions. "Where did my money go?" (Layer A) and "What moved through my account?" (Layer C) are genuinely different. A transfer between the user's own accounts is real cash-flow but zero consumer spending.

In the data model this is carried by `source` on the transaction (manual vs bank_import), by the recurring template being a separate entity that generates no transactions, and by the per-category flags in section 10.

---

## 4. Primary v0.0.1 consumer spending categories

These are the day-one defaults for manual entry. The set is intentionally small (14) so the picker stays fast. All are system categories (`is_system = true`, `user_id = null`). The user may later add their own categories, but these seed the app.

Convention for each entry: internal key | English label | Hebrew label placeholder | purpose | belongs | does not belong | examples | nature | Home | common confusion.

---

1. groceries
- Key: `groceries`
- English: Groceries
- Hebrew placeholder: קניות מזון / סופר
- Purpose: food and household staples bought to consume at home.
- Belongs: supermarket runs, fresh produce, dry goods, basic household consumables bought with groceries (cleaning, paper goods).
- Does NOT belong: restaurant/takeaway meals (that is `eating_out`); a big non-food homeware purchase (that is `home`).
- Examples: Shufersal, Rami Levy, Victory, Tiv Taam, Osher Ad, neighborhood makolet.
- Nature: mixed (mostly recurring necessity, some discretionary).
- Home: yes (commonly a top category).
- Common confusion: groceries vs eating out (buying food to cook = groceries; buying a prepared meal = eating out). A supermarket cafe meal is eating_out.

2. eating_out
- Key: `eating_out`
- English: Eating out
- Hebrew placeholder: אוכל בחוץ
- Purpose: prepared food and drink bought to eat now — restaurants, cafes, takeaway, delivery.
- Belongs: restaurants, cafes, bars, fast food, food delivery, coffee, ice cream.
- Does NOT belong: supermarket food to cook at home (`groceries`).
- Examples: Wolt, Golda, Aroma, Cofix, Landwer, Wolt/10bis delivery, a falafel stand.
- Nature: discretionary.
- Home: yes.
- Common confusion: eating_out vs groceries (see above); coffee beans bought at a supermarket are groceries, a coffee at Aroma is eating_out.

3. transport
- Key: `transport`
- English: Transport
- Hebrew placeholder: תחבורה
- Purpose: getting around — public transit, taxis, ride-hail, parking, tolls (non-fuel).
- Belongs: Rav-Kav top-ups, bus/train, taxi, ride-hail, parking, Route 6 toll, bike/scooter share.
- Does NOT belong: fuel and car upkeep (`car_fuel`); a flight or intercity trip that is part of travel (`travel`).
- Examples: Rav-Kav, Gett, Yango, Pango/Cellopark parking, Israel Railways, Bubble Dan.
- Nature: mixed.
- Home: yes.
- Common confusion: transport vs car_fuel (a bus ticket is transport; petrol is car_fuel). Keep these separate so the user can see car-ownership cost distinctly.

4. car_fuel
- Key: `car_fuel`
- English: Car / fuel
- Hebrew placeholder: רכב / דלק
- Purpose: the cost of owning and running a private car.
- Belongs: petrol/diesel, car wash, oil/garage service, tires, registration/licensing, car parking-as-a-car-cost if the user prefers it here (default: parking goes to `transport`).
- Does NOT belong: car insurance as a recurring commitment (model as a recurring template under `car_fuel` or `home`/insurance — see section 5); public transit (`transport`).
- Examples: Paz, Sonol, Delek, Dor Alon, Ten, a garage/mosach.
- Nature: mixed (fuel recurring, service lumpy).
- Home: yes.
- Common confusion: car_fuel vs transport (private car vs shared/public). Pick one rule and keep parking in transport by default.

5. shopping
- Key: `shopping`
- English: Shopping
- Hebrew placeholder: קניות
- Purpose: general retail goods — clothing, electronics, general merchandise.
- Belongs: clothes, shoes, electronics, accessories, general department-store purchases, online retail goods.
- Does NOT belong: groceries (`groceries`); furniture/home goods (`home`); personal-care/cosmetics (`personal_care`).
- Examples: Zara, Castro, Fox, KSP, Ivory, AliExpress/Amazon general goods, Terminal X.
- Nature: discretionary.
- Home: yes.
- Common confusion: shopping vs home (a lamp or sofa is home; a jacket is shopping); shopping vs personal_care (makeup/skincare is personal_care).

6. entertainment
- Key: `entertainment`
- English: Entertainment
- Hebrew placeholder: בידור ופנאי
- Purpose: leisure and going out — non-food experiences.
- Belongs: cinema, concerts, events, attractions, games, hobbies, sports/activity tickets, bars-as-night-out (or eating_out if mainly food).
- Does NOT belong: recurring streaming subscriptions (`subscriptions`); a restaurant meal (`eating_out`).
- Examples: Cinema City, Yes Planet, Ticketmaster/Leaan, an escape room, a museum, bowling.
- Nature: discretionary.
- Home: yes.
- Common confusion: entertainment vs subscriptions (a one-off movie ticket is entertainment; a monthly Netflix charge is subscriptions).

7. subscriptions
- Key: `subscriptions`
- English: Subscriptions
- Hebrew placeholder: מנויים
- Purpose: recurring digital/media/service subscriptions when they appear as actual spend.
- Belongs: streaming, music, cloud storage, app subscriptions, news/media memberships — the ACTUAL charge when logged.
- Does NOT belong: phone/internet utilities (model as recurring templates, typically under `home` or their own commitment — see section 5); a one-off app purchase (could be `shopping` or `entertainment`).
- Examples: Netflix, Spotify, YouTube Premium, iCloud/Google One, Disney+, Sting TV.
- Nature: discretionary (fixed cadence).
- Home: yes.
- Common confusion: subscriptions (Layer A actual charge) vs a recurring TEMPLATE (Layer B projection). A streaming template projects the commitment; when the real charge is entered manually it lands here as spend. See sections 3 and 5.

8. health
- Key: `health`
- English: Health
- Hebrew placeholder: בריאות
- Purpose: medical, dental, pharmacy, wellness, fitness.
- Belongs: pharmacy, doctor/dentist visits, glasses, supplements, gym (when paid as actual spend), physiotherapy.
- Does NOT belong: health insurance as a projected commitment (recurring template — section 5); cosmetics (`personal_care`).
- Examples: Super-Pharm, Be pharmacy, a private clinic, Holmes Place / Icon gym, an optometrist.
- Nature: mixed.
- Home: yes.
- Common confusion: health vs personal_care (a prescription is health; shampoo is personal_care). A gym membership is health by default.

9. education
- Key: `education`
- English: Education
- Hebrew placeholder: לימודים
- Purpose: learning — courses, tuition, books, training.
- Belongs: course fees, tuition, textbooks, online learning, professional certifications, kids' classes.
- Does NOT belong: a software subscription used for work/hobby (`subscriptions`); a recurring education subscription (template — section 5).
- Examples: Udemy/Coursera one-off course, a university payment, Steimatzky books, a music lesson.
- Nature: mixed.
- Home: yes (if material; otherwise minor).
- Common confusion: education vs subscriptions (a one-off course is education; a monthly learning subscription is a subscription/template).

10. home
- Key: `home`
- English: Home
- Hebrew placeholder: בית
- Purpose: the home itself — furniture, homeware, maintenance, and household one-offs (NOT rent; rent is a recurring commitment, section 5).
- Belongs: furniture, kitchenware, appliances, DIY/hardware, repairs, household goods that are not weekly groceries.
- Does NOT belong: rent (recurring template — section 5); weekly grocery consumables (`groceries`); utilities as recurring commitments (templates).
- Examples: IKEA, ACE/Home Center, Naaman, an electrician/handyman, a new microwave.
- Nature: mixed (mostly lumpy).
- Home: yes.
- Common confusion: home vs shopping (durable home goods vs personal goods); home vs groceries (a mop is home or groceries by user preference — default the everyday cleaning consumable to groceries, the durable item to home).

11. gifts
- Key: `gifts`
- English: Gifts
- Hebrew placeholder: מתנות
- Purpose: money spent on others — presents, donations, celebrations.
- Belongs: gifts, wedding/bar-mitzva money, charity/donations, flowers for someone.
- Does NOT belong: a gift to yourself (`shopping`); a transfer to your own account (Layer C, bank movement).
- Examples: a gift card purchase, a donation to a charity, flowers from a florist, "mtana" cash gift logged manually.
- Nature: discretionary.
- Home: yes (often small; surfaces when notable).
- Common confusion: gifts vs an outgoing bank transfer (money sent to a person as a gift, if logged manually, is gifts spend; the same line seen later in a bank import as a transfer is Layer C cash-flow, not double-counted).

12. travel
- Key: `travel`
- English: Travel
- Hebrew placeholder: נסיעות / חופשות
- Purpose: trips and vacations — flights, hotels, trip-specific costs.
- Belongs: flights, hotels, car rental, holiday activities, travel abroad spending, intercity vacation costs.
- Does NOT belong: the daily commute (`transport`); fuel for everyday driving (`car_fuel`).
- Examples: El Al, Booking.com, Airbnb, a tour, airport parking for a trip.
- Nature: discretionary.
- Home: yes (lumpy; prominent in travel months).
- Common confusion: travel vs transport (a vacation flight is travel; a daily bus is transport).

13. personal_care
- Key: `personal_care`
- English: Personal care
- Hebrew placeholder: טיפוח אישי
- Purpose: grooming, cosmetics, and personal upkeep services/products.
- Belongs: haircut/barber, cosmetics/skincare, nails, spa, toiletries when bought as personal care.
- Does NOT belong: medical/pharmacy prescriptions (`health`); general clothes (`shopping`).
- Examples: a barber/hairdresser, MAC/Sephora, a nail salon, perfume.
- Nature: discretionary.
- Home: yes.
- Common confusion: personal_care vs health (cosmetics vs medicine); personal_care vs shopping (toiletries vs apparel).

14. other_spending
- Key: `other_spending`
- English: Other spending
- Hebrew placeholder: הוצאות אחרות
- Purpose: a controlled safety valve for an actual purchase that genuinely fits none of the above — temporary only.
- Belongs: a one-off the user cannot place, logged quickly so the habit is not broken.
- Does NOT belong: anything that recurs or is large (those must be moved to a real category or trigger a new-category prompt — section 8); anything that is actually a bank movement (that is Layer C, not consumer spend).
- Examples: a miscellaneous one-off with no clear merchant category.
- Nature: mixed.
- Home: yes, but flagged for review if it grows (section 8).
- Common confusion: other_spending (Layer A consumer) vs other_bank_movement (Layer C cash-flow) vs uncategorized (no category chosen yet). See section 8 for the precise distinction.

Note on scope discipline: this set deliberately omits "Bills / Utilities" as a consumer-spend category. In manual-first v0.0.1, utilities (electricity, water, phone, internet, rent) are predictable commitments and are modeled as recurring TEMPLATES (Layer B, section 5), not as ad-hoc manual purchases. This keeps the consumer list short and avoids the trap of a "Bills" bucket that overlaps with both recurring commitments and bank movements. If the founder finds they routinely log one-off utility payments manually, a `bills_utilities` consumer category can be added later — but it is not seeded now, to keep the list small and justified.

---

## 5. Recurring commitment taxonomy

Recurring templates capture predictable commitments without waiting for months of history. They reuse consumer category KEYS for grouping but their amounts are projected commitments, not spend (Layer B, section 3).

FIRM DECISION (restated): in v0.0.1, recurring templates do NOT auto-create actual transactions. They produce projected commitments only. Actual transactions come only from manual entry or, later, from imports. This removes a whole class of double-counting/duplicate bugs (MANUAL_FIRST_MVP_REVISION section 7). Every row below answers "creates an actual transaction in v0.0.1?" with NO.

| Recurring item | Recommended category key | Fixed / variable | Contributes to committed amount? | Creates actual transaction in v0.0.1? |
|---|---|---|---|---|
| Gym | `health` | Fixed | Yes (if `counts_in_projection`) | No |
| Insurance (car/health/home/life) | `health` for health insurance; `car_fuel` for car insurance; `home` for home/contents insurance | Fixed (monthly or yearly) | Yes | No |
| Phone plan | `home` | Fixed | Yes | No |
| Internet | `home` | Fixed | Yes | No |
| Streaming | `subscriptions` | Fixed | Yes | No |
| Rent | `home` | Fixed | Yes | No |
| Loan payment | `home` (commitment view) — note: a bank-imported loan payment is Layer C `loan_payment`, see section 6 | Fixed | Yes | No |
| Software subscription | `subscriptions` | Fixed | Yes | No |
| Education subscription | `education` | Fixed | Yes | No |

Notes and rationale:
- Reuse of keys is intentional. A gym commitment and a one-off physio payment both live under `health`, but the gym appears in "Upcoming commitments" (projection) while the physio appears in "Spent so far" (actual). The KEY is shared; the LAYER differs. This keeps the category list tiny while preserving the spend-vs-commitment separation.
- Insurance is split by what it insures so the user sees true category cost (car insurance under `car_fuel` makes car ownership cost legible). This is an opinionated default; the user can re-point any template.
- `counts_in_projection` (per template, default true) controls whether a commitment is included in the month's projection. An annual fee the user accounts for separately can be excluded without deleting the template (MANUAL_FIRST_MVP_REVISION section 7).
- Inactive templates (cancelled subscription) stop contributing to projection but remain for history.
- Loan payment deliberately exists in TWO places with different meanings: a recurring commitment template (Layer B projection) and a bank-movement category (Layer C, section 6) when a real bank statement shows the debit. They are not the same row and must not be summed. v0.0.1 does not auto-reconcile them; the user sees commitment and (later) cash-flow separately.
- Rent is a commitment, never a consumer-spend category. There is intentionally no `rent` consumer category in section 4; rent lives only as a template under `home`.

---

## 6. Bank movement / cash-flow categories

These are the secondary, import-only categories (v0.0.2+). They mirror IMPORT_PIPELINE_SPEC section 13 exactly so the import pipeline and the taxonomy agree. All are system categories. They populate a cash-flow view, NOT the consumer-spend view. Matching signals are soft (description text + Hebrew operation code), never authoritative; user correction always wins (IMPORT_PIPELINE_SPEC sections 11 and 13).

1. income
- Key: `income`
- Purpose: incoming money that is earnings/benefit (not a transfer the user initiated).
- Belongs: salary/payroll, benefits, clearly-incoming non-transfer credits.
- Does NOT belong: a transfer between the user's own accounts (`incoming_transfer`).
- included_in_consumer_spending: false. included_in_cash_flow: true.
- Signals: `direction=credit`; salary/payroll description; op code like `222` (incoming).
- Future card-import compatibility: unaffected; income never appears in a card export.

2. incoming_transfer
- Key: `incoming_transfer`
- Purpose: money transferred INTO the account (own-account move or from another person).
- Belongs: incoming transfers (`העברה נכנסת`).
- Does NOT belong: salary (`income`).
- included_in_consumer_spending: false. included_in_cash_flow: true.
- Signals: `direction=credit`; description `העברה נכנסת`; op `222`.
- Future card-import compatibility: not present in card exports.

3. outgoing_transfer
- Key: `outgoing_transfer`
- Purpose: money transferred OUT of the account.
- Belongs: outgoing transfers (`העברה יוצאת`).
- Does NOT belong: a card settlement (`credit_card_settlement`); a purchase.
- included_in_consumer_spending: false. included_in_cash_flow: true.
- Signals: `direction=debit`; description `העברה יוצאת`; op `272`.
- Future card-import compatibility: a transfer to a person that the user ALSO logged manually as a `gifts` purchase is intentionally separate — Layer C cash-flow vs Layer A spend; not summed.

4. credit_card_settlement
- Key: `credit_card_settlement`
- English: Credit card payment / settlement
- Purpose: the single aggregate monthly payment to a card issuer — NOT the underlying purchases.
- Belongs: card settlement lines (`חיוב כרטיס אשראי`).
- Does NOT belong: any individual purchase (those are Layer A; from manual entry now, itemized card import later).
- included_in_consumer_spending: false (EXCLUDED). included_in_cash_flow: true.
- Signals: `direction=debit`; description `חיוב כרטיס אשראי`; op `162`. ALSO sets `is_card_settlement = true` (IMPORT_PIPELINE_SPEC section 14).
- Future card-import compatibility: THIS is the linchpin. When itemized card files arrive (v0.0.3), each purchase becomes Layer A spend; the bank-level settlement is already excluded, so the same money is never counted twice.

5. loan_payment
- Key: `loan_payment`
- Purpose: loan/mortgage repayment seen as a bank movement.
- Belongs: loan/mortgage debit (`הלוואה` / `משכנתא`).
- Does NOT belong: a recurring loan COMMITMENT template (Layer B, section 5) — same money concept, different layer, not summed.
- included_in_consumer_spending: false. included_in_cash_flow: true.
- Signals: `direction=debit`; description indicating loan/mortgage.
- Future card-import compatibility: not present in card exports.

6. interest_bank_fee
- Key: `interest_bank_fee`
- Purpose: bank-charged interest, fees, commissions.
- Belongs: fee/commission/interest lines (`עמלה` / `ריבית`).
- Does NOT belong: a consumer purchase.
- included_in_consumer_spending: false (cost of banking, not lifestyle spend). included_in_cash_flow: true.
- Signals: small `direction=debit` (occasionally credit) with fee/interest description.
- Future card-import compatibility: card-issuer fees in a future card export would be a separate decision; for v0.0.1/v0.0.2 this is bank-level only.

7. cash_deposit_withdrawal
- Key: `cash_deposit_withdrawal`
- Purpose: ATM/cash movement where the underlying purchase is unknown.
- Belongs: ATM/cash lines (`מזומן` / `כספומט`); direction sets deposit vs withdrawal.
- Does NOT belong: a known cash purchase the user manually categorized (that is Layer A spend).
- included_in_consumer_spending: false (the underlying spend is unknown; counting it as spend AND later logging the purchase would double-count). included_in_cash_flow: true.
- Signals: ATM/cash description or op.
- Future card-import compatibility: cash is invisible to card exports; remains bank-only.

8. other_bank_movement
- Key: `other_bank_movement`
- Purpose: the safe DEFAULT for an imported bank row that nothing confidently matches.
- Belongs: low-confidence/unclassified bank movements.
- Does NOT belong: anything that clearly matches a category above; consumer spend.
- included_in_consumer_spending: false. included_in_cash_flow: true.
- Signals: none confident (IMPORT_PIPELINE_SPEC section 13 default).
- Future card-import compatibility: bank-only fallback; the card-import equivalent would be `uncategorized` on Layer A, not this.

Layer-C rule: NONE of these eight count as consumer spending. They exist to make the account/cash-flow view correct without polluting "Spent so far." This is the clean separation the manual-first revision requires (MANUAL_FIRST_MVP_REVISION section 8).

---

## 7. Excluded-from-consumer-spending categories

The following must NOT count toward consumer-spending totals or category rankings. Each still has a legitimate home (cash-flow view or commitment view) so the user's full picture stays correct.

| Item | Why excluded from spend | Where it DOES appear |
|---|---|---|
| Credit card payment / settlement (`credit_card_settlement`, `is_card_settlement = true`) | It is an aggregate transfer to the issuer; the real purchases are/will-be counted separately as Layer A. Counting both double-counts. | Cash-flow view (Layer C). |
| Internal transfer (`outgoing_transfer` between own accounts) | Moving your own money is not spending. | Cash-flow view. |
| Incoming transfer (`incoming_transfer`) | Money in, not money spent. | Cash-flow view (and informs balance). |
| Loan principal movement (`loan_payment`, where applicable) | Principal repayment is a balance-sheet movement, not lifestyle consumption; only interest/fees are a cost. (Assumption: v0.0.1 does not split principal vs interest; the whole line stays out of consumer spend and is shown as cash-flow.) | Cash-flow view; the commitment appears in the projection via a template (Layer B). |
| Cash movement, underlying purchase unknown (`cash_deposit_withdrawal`) | Counting the ATM withdrawal AND the later manually-logged cash purchase would double-count. | Cash-flow view. |
| Refunds / reversals (if represented separately) | A refund offsets a prior purchase; if shown as its own positive line it must net against spend, not inflate income or stand alone as spend. (Assumption: v0.0.1 keeps refunds simple — a manual refund is entered as a negative-direction adjustment in the same category so the category net is correct; it is never a standalone "income".) | Reduces the relevant Layer A category net. |
| Recurring projected commitments not yet occurred (Layer B templates) | The money has not moved. Counting a projection as spend would overstate "Spent so far." | "Upcoming commitments" projection only. |

The mechanism that enforces this in v0.0.1: consumer-spend totals are computed only over transactions where `source = manual` (and later, itemized card imports) AND `is_card_settlement = false` AND the category is a Layer A consumer category. Bank-movement categories and recurring templates are queried for the cash-flow and projection views respectively, never folded into spend.

---

## 8. Other, Uncategorized, and Ambiguous policy

Four distinct states. Conflating them is how "Other" becomes a dumping ground, which this taxonomy explicitly forbids (MVP_EXECUTION_ALIGNMENT issue 14).

- Other spending (`other_spending`, Layer A): a CHOSEN consumer category for a real purchase that fits nothing else. A deliberate, temporary safety valve so Quick Add is never blocked.
- Other bank movement (`other_bank_movement`, Layer C): a bank-import row that classification could not confidently place. Cash-flow only; never consumer spend.
- Uncategorized (no category at all, `category_id = null`): a first-class state meaning "no category has been chosen yet." This is NOT a category and never appears in rankings as if it were one. It is a to-do, surfaced for the user to resolve.
- Ambiguous (import-time, IMPORT_PIPELINE_SPEC sections 7-8): an imported row the parser could not resolve (both credit/debit sides real, or a real amount equal to the placeholder). It is excluded from auto-import and surfaced for review. Ambiguity is a parsing state, not a category.

When each is allowed:
- `other_spending`: allowed at Quick Add when the user genuinely cannot place a purchase quickly. Encouraged to be rare.
- `other_bank_movement`: allowed only at import time as the safe default (Layer C).
- Uncategorized: allowed any time the user defers choosing — preferred over forcing a wrong category. Never silently coerced into Other (MANUAL_FIRST_MVP_REVISION section 12).
- Ambiguous: only an import concept; never produced by manual entry.

When the app should prompt for correction:
- Repeated merchant in Other: if the SAME merchant is logged to `other_spending` two or more times, prompt: "You've put [Merchant] in Other before — pick a category and we'll remember it." Two occurrences is the threshold (assumption: tuned low because the sole user benefits from early nudges; revisit if noisy).
- Large item in Other: any single `other_spending` transaction at or above a meaningful share of the month (assumption: a configurable threshold, e.g. the larger of a fixed floor or ~5% of month-to-date spend) prompts a one-tap recategorize, because a big unexplained item undermines the whole overview.
- Other/Uncategorized volume: when `other_spending` + uncategorized together exceed a threshold for the month (assumption: more than ~10% of the month's transaction COUNT, or more than 5 items, whichever is smaller for the solo user), Home surfaces a gentle "X items need a category" review prompt. This keeps analytics trustworthy without nagging on every entry.

Why repeated/large merchants must not stay in Other: the entire value of the app is telling the user where money went. A recurring or large amount hiding in Other silently corrupts the top-category and category-ranking outputs the user relies on. Moving it out (and creating a rule, section 9) is what turns the app from a labeller into a coach.

Why Other is temporary, not analytics: "Other spending" carries no behavioral meaning — it cannot tell the user anything actionable. It exists to keep entry fast, then to be emptied by correction. A healthy v0.0.1 has a small and shrinking Other.

---

## 9. User corrections and category rules

Corrections are how the system learns. Aligned with the CategoryRule entity (MANUAL_FIRST_MVP_REVISION section 9; PRD section 11): `match_type` (merchant_exact | contains), `match_value`, `category_id`, `priority`, `source` (system | user_correction).

How corrections create/update rules:
- Merchant exact match: the primary rule type. When the user assigns a category to a merchant and confirms "Always categorize [Merchant] as [Category]?", create/update a `merchant_exact` rule. This is the strongest, least-noisy signal.
- Merchant contains match: a broader rule for description fragments (useful for imported raw descriptions later, e.g. "WOLT" matching "WOLT TEL AVIV"). Lower precedence than exact because it can over-match.
- Recent merchant memory: the last category used for a merchant is remembered and offered as the Quick Add default even before a formal rule exists. This is the lightweight, no-friction path (MANUAL_FIRST_MVP_REVISION section 6); a confirmed correction promotes it to a real rule.
- Category auto-suggestion during Quick Add: when a known merchant is selected, pre-fill its category from (in order) an exact rule, then a contains rule, then recent-merchant memory, then the merchant's `default_category_id`. The user confirms or overrides in one tap.

Priority and rule type:
- Precedence (highest first): user_correction `merchant_exact` > user_correction `contains` > system `merchant_exact` > system `contains` > recent-merchant memory > merchant default > uncategorized.
- `source = user_correction` always outranks `source = system`. The user's explicit choice is authoritative over any seeded default (PRD principle 5; IMPORT_PIPELINE_SPEC section 13 — corrections are authoritative).

When NOT to create a rule automatically:
- Do not auto-create a rule for a one-off `other_spending` entry — wait for the section-8 repeat threshold.
- Do not auto-create a rule from a single edit without the explicit "always categorize" confirmation; a silent edit changes only that transaction. Rules are opt-in so the user is never surprised by future auto-categorization.
- Do not create a `contains` rule from a very short or generic fragment (assumption: minimum length / non-generic check) to avoid over-matching unrelated merchants.

Conflicting rules:
- If two rules match, the higher-priority rule wins by the precedence list above; ties broken by most-recently-updated (the newer correction reflects current intent).
- If a new user correction conflicts with an existing user rule for the same merchant, UPDATE the existing rule rather than stacking a second one, so a merchant maps to exactly one category at a time.
- Rules apply going forward by default; bulk re-categorization of existing transactions is offered as an explicit, optional action, never automatic (avoids silently rewriting history).

---

## 10. Category IDs and internal naming

Internal keys are English snake_case and STABLE even after Hebrew labels are added — labels are display only; keys are identity. Layer values: `consumer_spending` (A), `recurring_commitment` (B — note these reuse consumer keys, so they are not separate rows), `bank_movement` (C). All rows below are system categories (`is_system = true`, `user_id = null`).

Consolidated table (consumer + bank categories that get seeded):

| internal key | English label | Hebrew label placeholder | layer | in_actual_spending | in_committed_projection | in_cash_flow | is_system |
|---|---|---|---|---|---|---|---|
| groceries | Groceries | קניות מזון / סופר | consumer_spending | t | f | f | true |
| eating_out | Eating out | אוכל בחוץ | consumer_spending | t | f | f | true |
| transport | Transport | תחבורה | consumer_spending | t | f | f | true |
| car_fuel | Car / fuel | רכב / דלק | consumer_spending | t | f | f | true |
| shopping | Shopping | קניות | consumer_spending | t | f | f | true |
| entertainment | Entertainment | בידור ופנאי | consumer_spending | t | f | f | true |
| subscriptions | Subscriptions | מנויים | consumer_spending | t | f | f | true |
| health | Health | בריאות | consumer_spending | t | f | f | true |
| education | Education | לימודים | consumer_spending | t | f | f | true |
| home | Home | בית | consumer_spending | t | f | f | true |
| gifts | Gifts | מתנות | consumer_spending | t | f | f | true |
| travel | Travel | נסיעות / חופשות | consumer_spending | t | f | f | true |
| personal_care | Personal care | טיפוח אישי | consumer_spending | t | f | f | true |
| other_spending | Other spending | הוצאות אחרות | consumer_spending | t | f | f | true |
| income | Income | הכנסה | bank_movement | f | f | t | true |
| incoming_transfer | Incoming transfer | העברה נכנסת | bank_movement | f | f | t | true |
| outgoing_transfer | Outgoing transfer | העברה יוצאת | bank_movement | f | f | t | true |
| credit_card_settlement | Credit card payment / settlement | חיוב כרטיס אשראי | bank_movement | f | f | t | true |
| loan_payment | Loan payment | תשלום הלוואה | bank_movement | f | f | t | true |
| interest_bank_fee | Interest / bank fee | ריבית / עמלה | bank_movement | f | f | t | true |
| cash_deposit_withdrawal | Cash deposit / withdrawal | הפקדה / משיכת מזומן | bank_movement | f | f | t | true |
| other_bank_movement | Other bank movement | תנועה בנקאית אחרת | bank_movement | f | f | t | true |

Notes:
- `in_committed_projection` is `f` for every seeded category row, because projection is a property of a recurring TEMPLATE (the RecurringExpenseTemplate entity), not of a category. A template carries `counts_in_projection` and references one of the consumer keys above. The projection total is computed from templates, not from category flags. This is why Layer B has no separate rows here.
- `credit_card_settlement` additionally drives `is_card_settlement = true` on imported transactions (section 7).
- Uncategorized is the ABSENCE of a category (`category_id = null`), so it is intentionally not a row in this table.

---

## 11. Quick Add implications

The taxonomy must serve sub-five-second entry (MANUAL_FIRST_MVP_REVISION section 6). The category list is designed to be picked fast, or not picked at all.

- Recommended ordering on the picker: most-used-first for THIS user, computed from their own history, so the categories they actually use float to the top. Before history exists, a sensible default order leads with the highest-frequency everyday categories: Groceries, Eating out, Transport, Car / fuel, Shopping, then the rest.
- Recent categories: show the last few categories the user picked as quick chips at the top, independent of merchant.
- Merchant-based auto-suggestion: when a known merchant is chosen, the category is pre-filled from rules/memory (section 9); the user usually confirms without opening the picker at all. This is the dominant happy path for repeat merchants.
- Avoid too many categories on the first screen: only Layer A consumer categories appear in Quick Add. Bank-movement (Layer C) categories are NEVER offered in manual entry — they belong to import only. This keeps the manual picker at 14 options, not 22.
- Fallback when unsure: two equally valid escapes — leave it Uncategorized (resolve later) or pick Other spending. Uncategorized is preferred when the user expects to categorize later; Other when they want it "done." Neither blocks the save.
- Keeping entry under five seconds: amount-first with the keypad up, today as default date, one-tap recent merchant, category auto-filled. The realistic path is amount + tap merchant + save, with the category never manually chosen for a repeat. The 14-item ceiling exists precisely so that when the picker IS opened, the choice is fast.

---

## 12. Home dashboard implications

Home must pass the five-second test and must NEVER blend the three layers without labels (MANUAL_FIRST_MVP_REVISION section 10; PRD principle 1).

What Home can safely show in manual-first v0.0.1:
1. Actual manually entered spending this month — the headline number (sum of Layer A consumer spend; excludes settlements and templates by construction).
2. Committed recurring amount this month — the projection from active templates where `counts_in_projection = true` (Layer B), shown as a clearly separate, clearly labelled number.
3. Known total this month — actual + committed projection, presented so the two parts stay VISIBLY separate (e.g. "Spent X / Committed Y"), never merged into one ambiguous figure.
4. Top actual spending category — the single largest Layer A category, one tap into its transactions.
5. Recent transactions — the last few entries for quick recall and correction.
6. Upcoming recurring commitments — the next template charges due (Layer B), as a forward-looking list.

RULE (firm): actual spending and projected commitments must NEVER be blended without labels. Blending them is a correctness bug, not a styling choice. When bank cash-flow import arrives (v0.0.2+), it is shown in a SEPARATE cash-flow view, and card settlements are excluded from spend (section 7). In pure-manual v0.0.1, the cash-flow line is simply absent.

Suggested user-facing labels:
- "Spent so far" — Layer A actual spend this month.
- "Upcoming commitments" — Layer B projected commitments still due.
- "Known this month" — the clearly-split combination of the two.
- "Cash-flow view" — the separate Layer C view (v0.0.2+ only).
- "Spending detail" — the drill-down into Layer A categories and transactions.

---

## 13. Future itemized credit-card import compatibility

The taxonomy is designed so the v0.0.3 itemized card import slots in without revision:

- Card PURCHASES count as actual consumer spending (Layer A). Each line in an itemized per-card export is a real purchase with a real merchant and gets a Layer A category, exactly like a manual entry. They become the spending of record.
- Bank-level card SETTLEMENTS do NOT count as spend. They remain Layer C with `is_card_settlement = true`, already excluded (section 7). So when itemized purchases arrive, the aggregate settlement is already kept out — no double-count, by construction (IMPORT_PIPELINE_SPEC section 14).
- Manual transactions may need duplicate checks against future imported card purchases. A manually logged "Golda 33" and the same purchase later imported from the card file are the same money. v0.0.1 does not auto-reconcile (out of scope), but the schema's `source` field and dedup approach are retained so a future reconciliation/de-dup step can match them. (Assumption: reconciliation is v0.0.3 work; v0.0.1 only avoids the SETTLEMENT-vs-manual double count, which the flag already handles.)
- Merchant/category rules work across manual and imported transactions. The same CategoryRule (merchant_exact / contains) and merchant-to-category memory apply whether the row came from manual entry or an import, so the user's learned categorization carries over rather than being rebuilt per source.

---

## 14. Acceptance criteria

This taxonomy is complete when ALL hold:
1. Consumer categories (Layer A, section 4) are the PRIMARY v0.0.1 categories used by manual Quick Add.
2. Recurring commitments (Layer B, section 5) are modeled separately from actual spending and create NO actual transactions in v0.0.1.
3. Bank movement categories (Layer C, section 6) are secondary, import-only, and clearly separated from consumer spend.
4. Card settlements are excluded from consumer-spending totals via `is_card_settlement` (sections 6, 7, 13).
5. Other spending, Other bank movement, Uncategorized, and Ambiguous are clearly distinct, with a controlled-Other policy and concrete review thresholds (section 8).
6. Category keys are stable English snake_case, ready for seed data, each with a Hebrew label placeholder (section 10).
7. The taxonomy supports Quick Add under five seconds: small list, most-used ordering, merchant auto-suggestion, no Layer C clutter in manual entry (section 11).
8. The set is small enough to understand (14 consumer categories; growth justified, not reflexive).
9. The next DB schema can seed these system categories without immediate revision (the section 10 table is seed-ready, and `in_committed_projection` is correctly a template property, not a category flag).

---

## 15. Next recommended prompt

Firm recommendation: proceed to docs/MERCHANT_NORMALIZATION_SPEC.md next.

Justification: the manual-first pivot does NOT change the document order materially here, and merchant normalization is the immediate dependency of everything this taxonomy enables. The whole learning loop — recent-merchant memory, merchant-to-category auto-suggestion, and CategoryRule matching (section 9) — rests on a STABLE merchant identity. "Golda", "Golda Dizengoff", and a future imported "GOLDA*TLV" must collapse to one payee, or rules and category totals fracture. In manual-first this is arguably MORE urgent than under import-first, because the merchant the user types by hand (with typos, partial names, Hebrew/English variants) is now the PRIMARY key for auto-categorization, not a parsed bank description. Until normalization is specified, the schema cannot correctly model the Merchant entity's `normalized_name` / `raw_aliases`, and Quick Add's autocomplete cannot be built reliably.

I considered three alternatives and rejected each as less urgent right now:
- DATA_SOURCE_STRATEGY.md — valuable for articulating the manual / bank / card / open-banking layering, but the layering is already decided and captured (MANUAL_FIRST_MVP_REVISION sections 8 and 11, and this document's three-layer model). It can follow; it does not block code.
- DATABASE_SCHEMA_V0_0_1.md — must come AFTER merchant normalization, because the Merchant entity's fields depend on the normalization rules. Writing the schema first risks baking in a Merchant model the normalization spec then revises (same trap MVP_EXECUTION_ALIGNMENT section 8 warns about for categories).
- WIREFRAMES_V0_0_1.md for Quick Add — the five-second flow is important, but the flow depends on merchant autocomplete and category auto-suggestion behavior, which the merchant spec defines. Wireframes are better drawn once that behavior is pinned down.

Exact next prompt to send after approving this taxonomy:

> "Acting as the fintech-researcher agent with the product-architect agent, and using docs/PRD_V0_1.md as the long-term vision, docs/MANUAL_FIRST_MVP_REVISION.md as the governing v0.0.1 decision, docs/CATEGORY_TAXONOMY.md as the finalized taxonomy, and docs/IMPORT_PIPELINE_SPEC.md section 10 (description and counterparty normalization) as input, produce docs/MERCHANT_NORMALIZATION_SPEC.md for manual-first v0.0.1. Define how a user-typed merchant (and later an imported raw description) collapses to one normalized payee: normalization rules (whitespace, Hebrew/English variants, punctuation, casing, invisible/bidi chars, NFC), the Merchant entity's normalized_name vs raw_aliases handling, recent-merchant autocomplete behavior for Quick Add, how a merchant maps to a default category and to CategoryRules (consistent with CATEGORY_TAXONOMY section 9), de-duplication of near-identical merchants, worked Israeli examples (Wolt, Golda, Shufersal, Rami Levy, Paz/Sonol/Delek, Rav-Kav, Gett), and edge cases. Keep it small and practical; align with the 5-second Quick Add, the firm invariants (signed minor units, UTC metadata, user_id everywhere, raw transactions never embedded), and design for future Hebrew labels and RTL. Planning only, no code."

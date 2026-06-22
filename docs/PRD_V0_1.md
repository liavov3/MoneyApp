# Money App — Product Requirements Document (PRD) v0.1

Status: Formal specification. Decision-complete. No code, no screens, no implementation.
Source of truth: docs/PROJECT_PLAN.md (approved 2026-06-13)
Owner: Product Architect
Audience: All v0.1 agents (UX, database, AI/RAG, security, backend, mobile, QA)
Date: 2026-06-13

---

## 1. Product one-liner

Money App is a mobile personal-finance coach that turns imported transactions into a five-second answer to "Am I okay this month, what changed, and what is one thing I should do?"

---

## 2. Product vision

Money App becomes the calmest, clearest way for one person to understand and steadily improve their personal spending. It behaves like a coach in the pocket: it does the boring categorization work, tells a short monthly story, and ends every observation with a concrete action.

What makes it different:

- Different from spreadsheets: spreadsheets demand manual entry, formulas, and discipline, and they show data without meaning. Money App ingests files, categorizes automatically, and produces meaning (a monthly narrative plus actions), not rows.
- Different from banking apps: banking apps show one account at a time, use jargon, bury spending in long lists, and rarely tell you what to do. Money App collapses multiple sources into one simple monthly story and is opinionated about the single next action.

The long-term architecture (Account abstraction, aggregated MonthlySummary bridge, SQL/vector separation) is built so future automatic bank and wallet integrations can be added without a rewrite, but v0.1 is deliberately a small, personal, file-first product.

---

## 3. Target user

v0.1 is built for exactly one user: the founder, a single individual managing their own personal spending.

- Profile: comfortable exporting CSV/Excel from a bank or credit-card website, owns a smartphone, wants clarity rather than configuration.
- Mindset: wants to be told what matters and what to do, not asked to tag, set up, or learn financial jargon.
- Single user, single device account. No families, shared budgets, advisors, or paying customers in v0.1.

---

## 4. Core jobs-to-be-done

1. "Get my spending into the app without manual data entry pain." (import a file or quickly add one transaction)
2. "Tell me in five seconds whether I'm okay this month and what changed." (home dashboard)
3. "Show me where my money actually went, in plain categories I trust." (categorization I can correct)
4. "Warn me about things I'd otherwise miss." (recurring subscriptions, unusual spending)
5. "Tell me one realistic thing I can do to save." (actionable insight, not a chart)
6. "Let me ask questions about my own money and get straight, grounded answers." (AI coach)
7. "Keep my financial data private, and let me take it out or delete it." (trust, export, deletion)

---

## 5. MVP scope (v0.1)

v0.1 includes, and only includes, the following:

1. CSV/Excel transaction import with a guided, remembered column-mapping step.
2. Manual transaction entry (amount, date, merchant, category, optional note).
3. Merchant normalization (raw bank descriptions collapsed into a clean payee).
4. Auto-categorization by normalized merchant plus user-defined rules.
5. Category correction that creates or updates rules, so future imports learn.
6. Monthly dashboard: total spent this month plus change vs last month, with 1-3 actionable insights.
7. Category breakdown: categories ranked by spend, each with amount and month-over-month delta, drillable to transactions.
8. Month-over-month comparison: totals and per-category deltas, current vs previous month.
9. Recurring expense / subscription detection (same merchant, regular cadence, similar amount).
10. Unusual spending detection (amount or category anomalies vs the user's own history).
11. Plain-language, actionable insights (a small fixed set; every insight ends in a concrete action).
12. AI financial coach chat answering questions about the user's own spending, in plain language.
13. RAG over the user's aggregated MonthlySummary plus a curated, non-regulated financial-knowledge set.

Guardrails inside scope: single user, single device account; manual data in only (CSV/Excel/manual); coaching/budgeting advice only; any cited figure comes from deterministic SQL, never from the model or vector store.

Note on Budget entity: a lightweight per-category monthly target is modeled (section 11) but the in-app budgeting UI is deferred to late MVP and must not add home-screen complexity. The schema ships; the screen does not, unless it survives the 5-second-home test.

---

## 6. Explicitly out of scope for v0.1

The following are intentionally not built now. They may be architected for, but must not be implemented:

- Apple Pay / Apple Wallet / Apple FinanceKit sync.
- Live bank integrations and direct bank/card APIs.
- Open banking / account aggregation.
- Push notifications.
- Multi-user, shared budgets, household/family accounts.
- Public SaaS, sign-up funnel, billing, paid subscription tiers.
- Investment tracking, portfolio analytics, net-worth aggregation.
- Loan recommendations; investment, tax, credit, or any regulated financial advice.
- Complex/configurable dashboards, custom report builders, heavy charting.
- Desktop/web app — except minimal internal dev/admin tooling if genuinely needed for development.
- Hebrew/RTL localization (planned next; English-first for the v0.1 build).

---

## 7. Product principles (non-negotiable)

1. Five-second understanding: the home screen must answer "okay this month? what changed? what to do?" within five seconds. Defend it against creep.
2. Progressive disclosure: simple first; detail is always exactly one tap away, never on the home screen by default.
3. Minimal charts: prefer one number and one sentence over any chart. A chart must earn its place; the default is none.
4. Actionable insights: every insight ends in one concrete, realistic action. An insight with no action is a bug.
5. User control over categories: the user can always correct a category, and corrections teach the system via rules.
6. AI cites and explains its data: the coach states which data it used (e.g., "based on your May and April summaries") and never presents an unsourced number.
7. Privacy-first: financial data is sensitive PII by default; minimize what is collected, sent to the LLM, and logged.
8. No financial shame: the tone is coaching and neutral. No guilt-based UX, no scolding, no red "you failed" framing.

---

## 8. Core user flows (detailed)

First setup
1. User installs the app and creates a local single-user account.
2. Device-level unlock (biometric/passcode) is set as the gate before any financial data is shown.
3. One intro screen: "Import a file or add a transaction to begin." No bank linking, no long onboarding.
4. User picks a starting month.

Importing a CSV/Excel file
1. User selects a CSV or Excel file from the device.
2. App previews the first rows.
3. App asks the user to map columns: date, amount, description (and optionally currency). Mapping is remembered per source format (Account.source_format_ref).
4. App parses, normalizes merchants, de-duplicates against existing transactions, and auto-categorizes.
5. App shows a result summary: "Imported 142 transactions, 12 need a category."

Mapping columns
1. From the import preview, app proposes a best-guess mapping.
2. User confirms or adjusts which column is date, amount, description, currency.
3. User confirms date format and amount sign convention (debit positive/negative) if ambiguous.
4. App saves the mapping to the Account's source format for reuse.

Confirming imported transactions
1. App shows the import summary with counts (imported, duplicates skipped, uncategorized).
2. User can jump straight to the uncategorized items or accept and review later.
3. On accept, transactions are persisted under the ImportBatch.

Adding a manual transaction
1. User taps "+".
2. Enters amount and date; merchant entry auto-suggests a category from existing rules.
3. Optional note. Saves. Dashboard updates immediately.

Reviewing the home dashboard
1. User opens the app to Home.
2. Sees total spent this month, the change vs last month (one number, up/down), and 1-3 highlighted insights, each with an action.
3. Everything else is one tap away.

Reviewing categories
1. From Home, user taps "Categories."
2. Sees categories ranked by spend, each with amount and delta vs last month.
3. Taps a category to see its transactions for the month.

Correcting a category
1. User opens a transaction (or an uncategorized item).
2. Changes the category.
3. App asks: "Always categorize [Merchant] as [Category]?" If yes, it creates/updates a CategoryRule and future imports apply it.

Creating or updating a category rule
1. Triggered from a correction ("Always categorize...") or from Settings > category management.
2. User sets match type (merchant exact/contains) and target category.
3. Rule is saved with source = user_correction and applied to future categorization; existing transactions can optionally be re-categorized.

Asking the AI coach a question
1. User opens "Coach."
2. Types a question, e.g. "Why did I spend more this month?" or "Where can I cut back?"
3. Backend classifies intent; for any precise figure it runs deterministic SQL; in parallel it retrieves the user's relevant MonthlySummary chunks plus curated knowledge.
4. The coach answers in plain language, cites which data it used, and ends with one concrete action. It declines regulated/investment questions and redirects to budgeting.

Reviewing a monthly summary
1. User opens "Summary" (end of month or on demand).
2. Sees a short narrative: top categories, biggest change, new/cancelled subscriptions, unusual items, and 1-2 saving actions.

Exporting / deleting personal data
1. From Settings, user can export all their data in a portable format.
2. From Settings, user can permanently delete their account and all data.
3. Deletion cascades to transactions, summaries, embeddings, chat history, and backups per the deletion guarantee (section 15).

---

## 9. Screen inventory

Ten v0.1 screens. Home stays sparse; richness lives behind taps.

1. Onboarding / Auth
- Purpose: create the single-user account and set device unlock.
- Primary action: create account / unlock.
- Key visible info: one-line product intro; unlock prompt.
- Behind a tap: nothing (deliberately minimal).
- Empty state: first-run intro with "Import a file or add a transaction."
- Error state: auth/unlock failure with retry; lockout messaging after repeated failures.

2. Home (Dashboard)
- Purpose: the five-second answer.
- Primary action: read status; tap an insight's action.
- Key visible info: total spent this month; delta vs last month (one number, direction); 1-3 actionable insights.
- Behind a tap: Categories, Summary, Coach, the underlying transactions of an insight.
- Empty state: "No spending yet this month. Import a file or add a transaction."
- Error state: "Couldn't load your dashboard" with retry; never a blank or scary screen.

3. Import
- Purpose: bring a CSV/Excel file in and map it.
- Primary action: select file, confirm mapping, accept import.
- Key visible info: file preview; column mapping; import result summary (counts).
- Behind a tap: detailed list of uncategorized or duplicate rows.
- Empty state: file picker prompt with supported formats.
- Error state: unparseable file, unmapped required column, or zero rows — each with a specific, plain message and a way to fix the mapping.

4. Add Transaction
- Purpose: quick manual entry.
- Primary action: enter amount/date/merchant and save.
- Key visible info: amount, date, merchant, auto-suggested category, optional note.
- Behind a tap: category picker; rule-creation prompt.
- Empty state: clean form with sensible defaults (today's date).
- Error state: invalid amount/date inline validation; save failure with retry.

5. Categories
- Purpose: where the money went, ranked.
- Primary action: tap a category to drill in.
- Key visible info: categories ranked by spend, each with amount and delta vs last month.
- Behind a tap: Category Detail (transactions in that category).
- Empty state: "No categorized spending this month yet."
- Error state: load failure with retry.

6. Category Detail
- Purpose: the transactions inside one category for the month.
- Primary action: open a transaction to inspect or correct it.
- Key visible info: category total; list of transactions (merchant, date, amount).
- Behind a tap: Transaction Detail.
- Empty state: "No transactions in this category this month."
- Error state: load failure with retry.

7. Transaction Detail
- Purpose: inspect and correct a single transaction.
- Primary action: change category (and optionally create a rule).
- Key visible info: merchant, raw description, amount, date, category, source, note.
- Behind a tap: category picker; "Always categorize [Merchant] as [Category]?" rule prompt.
- Empty state: not applicable (always has a transaction).
- Error state: save failure with retry; clear handling if the transaction was deleted.

8. Insights / Summary
- Purpose: the monthly narrative.
- Primary action: read the story; tap a suggested action.
- Key visible info: top categories, biggest change, new/cancelled subscriptions, unusual items, 1-2 saving actions.
- Behind a tap: the transactions or category behind each insight.
- Empty state: "Not enough data yet for a summary — import at least one month."
- Error state: "Couldn't build this summary" with retry.

9. Coach (AI Chat)
- Purpose: conversational, grounded Q&A about the user's money.
- Primary action: ask a question.
- Key visible info: chat thread; the coach's answer with a stated data source and one action.
- Behind a tap: the referenced summary/category the answer used.
- Empty state: suggested starter questions (e.g., "Why did I spend more this month?").
- Error state: model/network failure with retry; graceful "I don't have data for that yet" for missing data; brief decline-and-redirect for out-of-scope questions.

10. Settings
- Purpose: control, trust, and management.
- Primary action: manage security, data, and categories.
- Key visible info: lock/biometric settings, category management, data export, data deletion, about.
- Behind a tap: category/rule management; export flow; deletion confirmation.
- Empty state: not applicable.
- Error state: export/delete failure with retry and clear status; deletion requires explicit confirmation.

---

## 10. Data requirements

- Transaction import: source file (CSV/Excel), parsed rows, column mapping per source format, date, amount (integer minor units), currency, raw description, account reference, import batch reference, dedup hash.
- Categorization: normalized merchant, category, category rules (match type, match value, priority, source), system default categories, user corrections.
- Monthly summaries: per user-month totals (spent/income), per-category amounts and deltas, top changes, recurring count, unusual item references, generated narrative text, computed timestamp.
- Recurring expense detection: merchant, transaction history per merchant, cadence, typical amount, last seen date, next expected date, status, confidence.
- Unusual spending detection: per-user historical distribution per category and per merchant, current transactions, thresholds, references to flagged transactions.
- AI chat: conversation and message history, role, content, references to which summaries/knowledge were used (not duplicated raw data), deterministic SQL results assembled as context.
- RAG: embeddings of MonthlySummary chunks (per user) and FinancialKnowledgeDocument chunks (system), with owner scope and user_id for isolation.
- Privacy/security: user identity and credential reference, encryption keys (in secure storage / secrets manager, never in DB rows), audit-safe event logs containing IDs and event types only.

---

## 11. Data model requirements

Conventions: money stored as integer minor units plus a currency code; all timestamps UTC; soft-delete where recovery may be needed before purge. Raw Transactions live in SQL only. MonthlySummary is the aggregated bridge. Embeddings index summaries plus curated knowledge, never raw rows.

User
- Purpose: account owner and security principal.
- Required fields: id, email, credential reference (auth hash/ref), base_currency, locale, settings (json), created_at.
- Indexes: unique(email).
- Privacy sensitivity: high (identity).
- Storage: SQL.

Account
- Purpose: a money source the user exports from; enables future multi-source and remembered mappings.
- Required fields: id, user_id, name, type (bank/card/cash), source_format_ref (remembered mapping), created_at.
- Indexes: (user_id).
- Privacy sensitivity: medium (account names can identify institutions).
- Storage: SQL.

ImportBatch
- Purpose: one import event; groups transactions for traceability and rollback.
- Required fields: id, user_id, account_id, source_filename_ref, row_count, imported_count, duplicate_count, uncategorized_count, status, created_at.
- Indexes: (user_id, created_at).
- Privacy sensitivity: medium (filenames may contain PII; store a reference, not raw content).
- Storage: SQL.

Transaction
- Purpose: a single spend/income line; the atomic unit.
- Required fields: id, user_id, account_id, posted_date, amount_minor, currency, raw_description, merchant_id (nullable), category_id (nullable), source (import/manual), import_batch_id (nullable), dedup_hash, note (nullable), is_recurring (flag), created_at, updated_at.
- Indexes: (user_id, posted_date), (user_id, merchant_id), (user_id, category_id), unique(user_id, dedup_hash).
- Privacy sensitivity: high (core financial PII).
- Storage: SQL only. Never embedded.

Merchant
- Purpose: normalized payee derived from raw descriptions; anchor for rules and recurring detection.
- Required fields: id, user_id, normalized_name, raw_aliases (json/array), default_category_id (nullable), created_at.
- Indexes: (user_id, normalized_name).
- Privacy sensitivity: high (reveals spending behavior).
- Storage: SQL.

Category
- Purpose: spending grouping shown to the user.
- Required fields: id, user_id (null = system default), name, parent_id (nullable), icon, is_system.
- Indexes: (user_id), (is_system).
- Privacy sensitivity: low for system categories; medium for user-named categories.
- Storage: SQL.

CategoryRule
- Purpose: learned mapping from merchant/pattern to category; powers auto-categorization and learning.
- Required fields: id, user_id, match_type (merchant_exact/contains/regex), match_value, category_id, priority, source (system/user_correction), created_at.
- Indexes: (user_id, priority), (user_id, match_type).
- Privacy sensitivity: medium (match values can be merchant PII).
- Storage: SQL.

Budget
- Purpose: optional per-category monthly target (schema ships in v0.1; UI deferred to late MVP).
- Required fields: id, user_id, category_id, period (year_month), limit_minor, created_at.
- Indexes: (user_id, period), (user_id, category_id).
- Privacy sensitivity: medium.
- Storage: SQL.

MonthlySummary
- Purpose: precomputed per-month rollup; the safe aggregated context the AI reads.
- Required fields: id, user_id, year_month, total_spent_minor, total_income_minor, per_category (json: category to amount + delta), top_changes (json), recurring_count, unusual_items (json refs), narrative_text, computed_at.
- Indexes: unique(user_id, year_month).
- Privacy sensitivity: medium-high (aggregated but still personal).
- Storage: SQL; its narrative/per-category chunks are also embedded into the vector store.

RecurringExpense
- Purpose: detected subscription/recurring charge.
- Required fields: id, user_id, merchant_id, cadence (monthly/weekly/annual), typical_amount_minor, last_seen_date, next_expected_date, status (active/cancelled), confidence.
- Indexes: (user_id, status), (user_id, merchant_id).
- Privacy sensitivity: high (reveals services used).
- Storage: SQL.

Insight
- Purpose: a generated, user-facing observation with a recommended action (the unit behind dashboard/summary cards).
- Required fields: id, user_id, year_month, type (enum, see section 14), title, body_text, action_text, severity, source_refs (json: transaction/category/summary refs), status (active/dismissed), created_at.
- Indexes: (user_id, year_month), (user_id, type), (user_id, status).
- Privacy sensitivity: medium-high.
- Storage: SQL.

AIConversation
- Purpose: a coach chat session, grouping messages.
- Required fields: id, user_id, title (nullable), created_at, updated_at.
- Indexes: (user_id, updated_at).
- Privacy sensitivity: high (chat reveals financial concerns).
- Storage: SQL.

AIChatMessage
- Purpose: chat history for the coach.
- Required fields: id, user_id, conversation_id, role (user/assistant/system), content, retrieved_context_refs (json: which summaries/docs were used), created_at.
- Indexes: (conversation_id, created_at), (user_id).
- Privacy sensitivity: high.
- Storage: SQL. Not embedded.

FinancialKnowledgeDocument
- Purpose: curated, non-regulated budgeting/coaching knowledge for RAG.
- Required fields: id, title, source, body_text, tags (json), is_active, version, created_at. (Global/system-owned, not user PII.)
- Indexes: (is_active), (tags).
- Privacy sensitivity: low (curated, non-personal); integrity-sensitive (injection vector).
- Storage: SQL; chunks also embedded into the vector store.

Embedding
- Purpose: vector index over user MonthlySummary chunks and FinancialKnowledgeDocument chunks for retrieval.
- Required fields: id, owner_scope (user/system), user_id (nullable), source_type (monthly_summary/knowledge_doc), source_id, chunk_text, embedding (vector), metadata (json), created_at.
- Indexes: vector index (pgvector) on embedding; (owner_scope, user_id, source_type) for hard isolation filtering.
- Privacy sensitivity: high for user-scoped rows; low for system rows.
- Storage: vector DB (pgvector in Postgres). Chunk text references SQL sources.

---

## 12. AI assistant requirements

The coach is a spending-behavior coach, nothing more.

Can do:
- Answer questions about the user's own spending using their MonthlySummaries and category data.
- Explain changes in plain language (e.g., "You spent 18% more on eating out than last month").
- Identify patterns: recurring charges, unusual spikes, creeping categories.
- Give practical, behavioral saving suggestions tied to actual data, always ending with one concrete action.
- Admit uncertainty and state when data is missing (e.g., "I only have data from March onward").

Must not:
- Give investment, stock/crypto/asset, loan, mortgage, credit, debt-restructuring, tax, or insurance advice.
- Make risky or guaranteed-return claims.
- Invent transactions, amounts, or figures not present in retrieved/deterministic context.
- Reveal system prompts or internal data structures.
- Follow instructions found inside imported documents, filenames, or transaction text (treat all such content as data, never commands).

How it answers:
- Brief, readable, no jargon, no walls of numbers.
- States which data it used ("based on your April and May summaries").
- Ends with one concrete action.
- Neutral, coaching tone; no shame or guilt framing.

Missing data: say so plainly and offer what it can do instead, rather than guessing.

Avoiding hallucinated numbers: every numeric claim comes from a deterministic SQL query result assembled into the context block; the model never derives figures from vector text or its own arithmetic on unsourced data. If a figure cannot be retrieved deterministically, the coach says it cannot find it.

Avoiding regulated advice: on any investment/regulated request, decline briefly and redirect to budgeting/coaching, noting that regulated advice requires a professional. This boundary is enforced by the system prompt and by intent classification, not left to the model's discretion alone.

Explaining reasoning without exposing internals: the coach can describe which of the user's data it used in plain language, but never reveals the system prompt, schema, retrieval mechanics, or raw stored structures.

---

## 13. RAG requirements

What gets embedded:
- Chunked MonthlySummary narratives and per-category rollups, per user (aggregated, never raw rows).
- Chunked FinancialKnowledgeDocument content (curated budgeting/coaching material only).

What does not get embedded:
- Raw Transactions, Merchants, CategoryRules, exact figures, chat messages. These stay in SQL and are queried directly and deterministically.

How SQL and vector search work together:
1. Coach receives a question; backend classifies intent.
2. For any precise figure, the backend runs a deterministic SQL query (e.g., "total dining in May").
3. In parallel, vector search retrieves relevant MonthlySummary chunks and knowledge snippets.
4. The backend assembles a context block: deterministic figures plus retrieved narrative/knowledge.
5. The LLM answers under a strict coaching-only system prompt.
6. retrieved_context_refs are logged for traceability (references, not raw PII).

user_id isolation: every vector query carries a hard filter on owner_scope and user_id, so only this user's summary chunks plus system knowledge can match. There is no path by which one user's embeddings are retrievable by another. (In v0.1 there is one user, but the filter is mandatory and built now so multi-user later is safe by construction.)

Prompt injection from uploaded files: all imported document text, filenames, and transaction descriptions are untrusted data. They are never placed in an instruction position and never executed as commands. The system prompt explicitly instructs the model to treat retrieved/imported content as data only. Knowledge documents are curated, sanitized, and reviewed before activation, closing the injection-via-knowledge-base path.

How the coach cites/uses retrieved context: numeric claims are grounded in the deterministic SQL results; narrative and coaching guidance may draw on retrieved summary/knowledge chunks; the coach states which data it used in plain language and never asserts an unsourced figure.

---

## 14. Insights engine requirements

v0.1 ships a small fixed set of insight types. Each ends in a concrete action. Tone is neutral and coaching, never shaming.

1. Top spending category
- Trigger: per current-month MonthlySummary, identify the category with the highest spend.
- Required data: current month per-category totals.
- Example message: "Your biggest category this month is Groceries at 1,420."
- Recommended action: "Tap to see what's inside Groceries."

2. Category increase vs previous month
- Trigger: a category's current-month spend exceeds the previous month by a meaningful threshold (absolute and percentage floor, defined in the insight-rule spec) to avoid noise.
- Required data: current and previous month per-category totals.
- Example message: "Eating out is up 18% vs last month (+95)."
- Recommended action: "Review eating-out transactions and set a soft limit."

3. Recurring subscription detected
- Trigger: RecurringExpense detection finds a same-merchant, regular-cadence, similar-amount series above the confidence threshold; flag new ones especially.
- Required data: per-merchant transaction history, cadence, typical amount, confidence.
- Example message: "Looks like a new recurring charge: StreamingCo, ~45/month."
- Recommended action: "Confirm it's a subscription, or review whether you still use it."

4. Unusual transaction
- Trigger: a transaction's amount is an outlier vs the user's own history for that category/merchant (anomaly thresholds from the detection spec).
- Required data: per-category/per-merchant historical distribution; current transactions.
- Example message: "Unusual: a 320 charge at HomeStore, much larger than usual for Home."
- Recommended action: "Check this transaction is correct."

5. Spending pace warning
- Trigger: projected month-end spend (current pace vs days elapsed) is meaningfully above the typical month, against the user's own history.
- Required data: month-to-date spend, days elapsed, prior-month totals.
- Example message: "At this pace you'll spend about 12% more than last month."
- Recommended action: "Pick one category to ease off for the rest of the month."

6. Simple saving opportunity
- Trigger: a recurring charge or a clearly elevated discretionary category presents a realistic, behavior-based reduction.
- Required data: recurring expenses and/or elevated discretionary category totals.
- Example message: "You have 3 active subscriptions totaling 110/month."
- Recommended action: "Review subscriptions; cancelling one could save ~45/month."

7. End-of-month summary
- Trigger: month rollover, or on demand from the Summary screen.
- Required data: full current-month MonthlySummary (top categories, biggest change, recurring changes, unusual items).
- Example message: "May recap: top categories Groceries and Eating out; biggest change was Eating out (+18%); 1 new subscription; 1 unusual charge."
- Recommended action: "Set one small goal for next month."

Thresholds and exact heuristics (percentage floors, confidence cutoffs, anomaly bounds) are owned by fintech-researcher in the insight-rule spec and tuned to minimize noise; the engine emits at most a few insights at a time to protect the 5-second home.

---

## 15. Privacy and security requirements

Sensitive data classification: transaction amounts, descriptions, merchant data, account names, monthly summaries, recurring/subscription data, insights, and chat content are all sensitive PII. Credentials and keys are secrets.

Must never be logged: raw transaction descriptions, identity-linked amounts, full chat content, file contents, filenames with PII, or any direct identifiers. Logs contain IDs and event types only; scrub before logging.

Secret management: no secrets in the repo. Use environment variables / a secrets manager. LLM API keys are server-side only and never shipped in the mobile app. Encryption keys live in the secrets manager / device secure storage (Keychain/Keystore), never in database rows.

Encryption: encrypt data at rest (database-level); TLS in transit; application-layer encryption for the most sensitive fields (raw_description, account identifiers) where practical; device secure storage for client tokens and keys.

Local/dev/prod separation: distinct configs and databases per environment; dev never points at real personal data without explicit intent; seed/dev data is synthetic.

Data export: the user can export all their data in a portable format from Settings.

Data deletion: the user can permanently delete their account and all data. Deletion cascades to transactions, summaries, embeddings, chat history, and backups. Backups carry the same deletion guarantee.

AI provider data handling assumptions: send the minimum necessary context (aggregated summaries plus deterministic figures, not full raw history). Prefer an LLM provider with a no-training, no-retention policy; the choice is documented in Phase 5. Strip direct identifiers from prompts where possible.

Threats specific to RAG and uploaded files: prompt injection via uploaded documents, filenames, or transaction descriptions (mitigated by treating all such content as data, never instructions); injection via the knowledge base (mitigated by curation, sanitization, and review before activation); cross-user retrieval (mitigated by a mandatory hard user_id/owner_scope filter on every vector query); over-sharing raw PII with the LLM (mitigated by the aggregated-summary context boundary).

---

## 16. Technical architecture decision

Confirmed (firm), consistent with the approved plan:

- Mobile: Expo React Native + TypeScript.
- Backend: a single FastAPI (Python) service.
- Database: PostgreSQL with the pgvector extension (one engine for relational data and vector search).
- API: REST/JSON.
- No microservices, no premature queues or scaling. Background jobs added only when import/summary computation actually requires them.

Why this is the best MVP stack:
- The product's center of gravity is data processing plus RAG plus LLM orchestration. Python's ecosystem (pandas for CSV/Excel parsing, embeddings, RAG tooling, pgvector clients) is strongest here and saves the most time over the project's life.
- Expo React Native gives fast mobile iteration for a solo developer and a clean path to future RTL/Hebrew support.
- One Postgres engine with pgvector keeps the SQL-versus-vector separation clean without running a second datastore.
- A single FastAPI service with one REST boundary keeps each layer in its best-fit language with minimal ops for a solo project; microservices and queues would be premature complexity.

---

## 17. Acceptance criteria

v0.1 is ready when a single user can, end to end:

1. Import a CSV/Excel file: select it, map columns (mapping remembered), and see a result summary with imported/duplicate/uncategorized counts.
2. See categorized spending: imported and manual transactions are auto-categorized by merchant/rules, with uncategorized items clearly surfaced.
3. Correct categories: change a transaction's category and optionally create a rule that auto-applies to future imports.
4. View the monthly dashboard: open Home and within five seconds see total spent this month, the change vs last month, and 1-3 actionable insights.
5. See actionable insights: recurring subscriptions and unusual spending are detected, and each insight ends in a concrete action; a monthly summary narrative is available.
6. Ask the AI coach: pose natural-language questions and receive plain-language answers grounded in real data, where every cited figure comes from deterministic SQL, the coach states which data it used, declines regulated advice, and ends with one action.
7. Export/delete data: export all personal data and permanently delete the account, with deletion cascading to summaries, embeddings, chat, and backups.

Cross-cutting acceptance: money handled as integer minor units; timestamps UTC; raw transactions never embedded; no PII in logs; no secrets in the repo.

---

## 18. Development phases

Phase 0 — Product docs
- Owner: product-architect (with fintech-researcher, mobile-ux-designer).
- Deliverables: this PRD; UX wireframes/specs for the 10 screens with a 5-second Home; default category taxonomy; recurring/unusual detection heuristics and insight-rule spec.
- Definition of done: PRD approved; wireframes cover all screens with empty/loading/error states; taxonomy and insight-rule spec aligned with v0.1 scope. No code.

Phase 1 — Repo and architecture setup
- Owner: backend-api-engineer (with react-native-engineer, database-engineer, security-privacy-engineer).
- Deliverables: repo structure; Expo app skeleton; FastAPI skeleton; Postgres + pgvector; local/dev/prod environments; auth scaffolding; secrets handling; agreed REST API contract.
- Definition of done: running skeletons across mobile and backend; environments separated; secrets externalized; API contract documented. No product features yet.

Phase 2 — Database and import pipeline
- Owner: database-engineer (with backend-api-engineer, react-native-engineer).
- Deliverables: full schema and migrations (section 11); CSV/Excel import with column mapping; merchant normalization; deduplication; manual entry; persistence.
- Definition of done: a real file imports end to end with remembered mapping, dedup, and correct minor-units/UTC handling; manual transactions save.

Phase 3 — Mobile dashboard and categories
- Owner: react-native-engineer (with backend-api-engineer, database-engineer, mobile-ux-designer).
- Deliverables: auto-categorization and rules; category correction that learns; monthly-by-category view; Home dashboard; month-over-month comparison.
- Definition of done: Home passes the 5-second test; categories rank with deltas; correcting a category creates/updates a rule that applies to future imports.

Phase 4 — Insights engine
- Owner: backend-api-engineer (with fintech-researcher, react-native-engineer).
- Deliverables: recurring-expense detection; unusual-spending detection; MonthlySummary computation; the seven insight types (section 14); Insights/Summary screen.
- Definition of done: recurring and unusual items are detected on real data; each insight has a concrete action; monthly summary narrative generates.

Phase 5 — AI chat and RAG
- Owner: ai-rag-engineer (with backend-api-engineer, security-privacy-engineer, react-native-engineer).
- Deliverables: embeddings over summaries + knowledge docs; retrieval pipeline with hard user_id isolation; deterministic SQL for figures; coach chat with guardrails; Coach UI; documented LLM provider choice.
- Definition of done: coach answers grounded questions; every cited number is from deterministic SQL; regulated advice is declined and redirected; injection content is treated as data; no cross-scope retrieval.

Phase 6 — Security, QA, polish
- Owner: security-privacy-engineer (with qa-tester, react-native-engineer, backend-api-engineer, mobile-ux-designer).
- Deliverables: security hardening; data export/delete with cascade; log scrubbing verification; end-to-end and edge-case testing; performance pass; polish; RTL/Hebrew prep.
- Definition of done: all acceptance criteria (section 17) pass; export/delete cascades verified including embeddings and backups; no PII in logs; v0.1 stable.

product-architect stays involved across all phases to guard scope and acceptance criteria.

---

## 19. Risks and mitigations

- CSV/Excel format variability (locales, date/number formats, sign conventions, multi-currency): guided, remembered per-source mapping; explicit date-format and amount-sign confirmation; pandas-based parsing; single currency assumed for v0.1 with currency stored for the future.
- Bad categorization (cold start before rules exist): system default rules plus fast, learning user corrections; uncategorized items clearly surfaced, never silently mis-bucketed.
- AI hallucination: deterministic SQL for every cited figure; the model never invents numbers; "I can't find that" over guessing.
- RAG privacy leaks: only aggregated summaries embedded (never raw rows); mandatory hard user_id/owner_scope filter on every vector query; minimum context sent to the LLM.
- Scope creep: the section 6 out-of-scope list and the product principles are enforced by product-architect across all phases; Budget UI deferred; new features must pass the 5-second-home and one-action tests.
- Overcomplicated UX: minimal charts; progressive disclosure; at most a few insights at once; Home defended against creep.
- Sensitive data handling: all financial data classified as PII; encryption at rest and in transit; no PII in logs; no secrets in the repo; server-side LLM keys; export and cascading deletion including embeddings and backups.

---

## 20. Next recommended prompt

Send this after approving the PRD (Phase 0 UX + taxonomy, before any code):

> "Acting as the mobile-ux-designer agent, using docs/PRD_V0_1.md as the source of truth, produce low-fidelity wireframes and screen specs for all 10 MVP screens, with special focus on a Home (Dashboard) that lets the user understand their financial situation in under 5 seconds. For each screen define purpose, key elements, primary action, what is hidden behind progressive disclosure, and empty/loading/error states. Do not write code. Then, acting as the fintech-researcher agent, propose the default spending-category taxonomy and the detection heuristics and thresholds for recurring-expense detection, unusual-spending detection, and the seven insight types in section 14. Keep everything aligned with the product principles and v0.1 scope. Planning and design only."

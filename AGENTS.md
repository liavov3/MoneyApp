# MoneyApp repository instructions

## Product

- MoneyApp is a manual-first personal-finance application: Expo React Native in `mobile/`, FastAPI in `backend/`, and Neon/Postgres.
- The primary product KPI is that a normal expense can be entered in approximately 3–5 seconds.
- Financial correctness, privacy, and trustworthy totals take priority over UI convenience.

## Financial invariants

- Store and calculate money as signed integer agorot in `amount_minor`. Parse user-facing decimal input exactly; never use floating-point arithmetic or silent rounding for authoritative money values.
- Preserve the established signs: expenses are negative; income/refund/adjustment behavior must match the current contract and tests. Goals are positive magnitudes, not transactions.
- Authoritative totals must be computed from the complete server-side dataset. Never derive Home, monthly, income, savings, or other authoritative totals from a truncated or paginated transaction list.
- Actual transactions and recurring projections are separate domains. Never blend them into one unlabeled total, and recurring templates must not create actual transactions unless a future contract explicitly changes that rule.
- Month calculations use date-only financial dates and explicit `[month_start, next_month_start)` boundaries.

## Contracts and cross-layer changes

- Treat `docs/API_CONTRACT_V0_0_1.md` and `docs/DATABASE_SCHEMA_V0_0_1.md` as frozen until the user explicitly authorizes a contract revision.
- For every API, schema, request/response, or cross-layer behavior change, reconcile all affected layers: API contract, database/model/migrations, backend schemas/routes, mobile API client/types, consumers, tests, and documentation.
- Detect and report contract drift with exact files/sections. Do not silently choose the implementation, tests, or documentation as the source of truth.
- Preserve server-resolved ownership, ownership-as-404, generic error envelopes, and privacy-safe logging. Never log tokens, raw merchant input, notes, amounts, or database credentials; never expose secrets, and return sensitive fields only when the contract requires them.

## Change discipline

- Prefer small, targeted, reviewable slices. Do not broadly refactor product code, modify unrelated files, or implement adjacent roadmap items without explicit scope.
- Do not change frozen contracts, database schema, or application behavior implicitly.
- Do not perform dependency major-version upgrades unless explicitly requested. Never use a forced dependency fix as routine remediation.
- Keep local secrets in ignored `.env` files; never print, stage, or commit them.

## Skills and verification

- Use `moneyapp-contract-guard` for API/schema/cross-layer work, `moneyapp-money-correctness` for financial behavior, `moneyapp-capture-loop` for transaction-entry UX, and `moneyapp-verification` after changes.
- Backend commands run from `backend/` with `.\.venv\Scripts\python.exe -m <pytest|alembic|uvicorn>`.
- Mobile checks run from `mobile/`; the baseline static check is `npm run typecheck`.
- Use targeted tests for narrow changes and the full backend suite for high-risk financial, schema, auth, or cross-layer changes. Report every skipped or unavailable check.

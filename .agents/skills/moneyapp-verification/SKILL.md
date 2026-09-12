---
name: moneyapp-verification
description: Select and run proportionate validation after MoneyApp changes. Use after implementation or fixes to cover backend tests, TypeScript, mobile runtime behavior, financial edge cases, and cross-layer agreement without defaulting blindly to every expensive suite.
---

# MoneyApp Verification

Match validation depth to the risk and changed surface. Do not claim completion when a required check was skipped, unavailable, or database-disconnected.

## Validation by surface

- Backend logic or routes: run the narrowest relevant pytest file/tests first. Use the full backend suite for financial aggregates, auth/ownership, schema, shared domain helpers, or cross-cutting API changes.
- Schema or migration changes: validate Alembic metadata and migration state, exercise upgrade behavior against the authorized development/test database, and run schema/constraint tests. Never mutate a database outside the task's authorization.
- Mobile TypeScript: run `npm run typecheck` from `mobile/`.
- Mobile UI or navigation: also exercise the changed flow in Expo or a production bundle when appropriate; verify loading, empty, error, success, keyboard, and RTL behavior.
- API or cross-layer changes: validate backend response shape, mobile client/types, every consumer, tests, and docs together using `moneyapp-contract-guard`.
- Financial behavior: apply `moneyapp-money-correctness` and verify exact agorot results, signs, month boundaries, full-dataset aggregation, and actual/projected separation.

## Choosing targeted versus full validation

Use targeted checks for a narrow component, copy, or isolated route change when shared behavior is untouched. Use the full relevant suite when the change affects money parsing, totals, Home, recurring projections, auth, persistence, migrations, shared API types, or several consumers.

Never treat database-backed tests that skipped as a green integration result. Keep secrets out of command output and report commands, pass/fail counts, skipped checks, and remaining runtime gaps.

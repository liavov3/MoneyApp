---
name: moneyapp-contract-guard
description: Trace and reconcile MoneyApp API, schema, request/response, or cross-layer behavior changes across contracts, backend, mobile, tests, and docs. Use before implementing or reviewing such changes; report drift instead of choosing a source of truth silently.
---

# MoneyApp Contract Guard

Use this workflow whenever a task changes or depends on an API, database schema, request/response model, or behavior shared by backend and mobile.

## Before implementation

1. Identify the relevant frozen contract sections and product specifications in `docs/`.
2. Trace the existing path end-to-end:
   - SQLAlchemy models and Alembic migrations;
   - FastAPI request/response models, routes, domain helpers, and error shapes;
   - `mobile/src/api.ts`, `mobile/src/types.ts`, and every consumer;
   - backend and mobile tests;
   - repository instructions and feature documentation.
3. Write down the current request, stored representation, response, and consuming UI behavior.
4. Compare every layer. If they disagree, report the exact files/sections and the user-visible consequence. Stop before behavior changes that require selecting a new source of truth.

Never repair drift by silently editing a frozen contract or by assuming passing tests define the intended behavior.

## During implementation

- Keep the slice atomic and update every authorized affected layer together.
- Preserve money, ownership, error-envelope, and privacy invariants from `AGENTS.md`.
- Do not add compatibility shims or duplicate fields unless the agreed contract requires them.

## Before completion

- Repeat the end-to-end trace against the diff.
- Confirm request and response names, optional/null semantics, status codes, errors, and consumer behavior agree.
- Run validation through `moneyapp-verification` and report any intentional remaining drift.

Return a concise trace summary, detected drift, agreed change surface, and validation evidence.

# MoneySaver — Money App backend (v0.0.1, manual-first)

Personal-finance backend. **FastAPI + SQLAlchemy 2.x (async) + Alembic +
PostgreSQL (pgvector installed, unused)**. Built strictly against the frozen
specs in `docs/`. Single-user, manual-first MVP — no AI, import, or Home yet.

## Layout

```
backend/
  app/
    config.py        # settings; DATABASE_URL externalized + asyncpg DSN normalization
    db.py            # async engine / session (process-global, lazily built)
    errors.py        # standard error envelope + exception handlers (API_CONTRACT §5)
    logging_utils.py # privacy-safe logging (allow-list keys only)
    middleware.py    # request_id + safe access log
    models.py        # SQLAlchemy models = Alembic metadata target
    money.py         # Decimal-only amount -> signed agorot (API_CONTRACT §14)
    auth.py          # server-resolved dev principal (Bearer token -> user_id)
    seed_data.py     # canonical 22 categories
    main.py          # FastAPI app, mounted at /api/v1
    routers/         # health.py, categories.py, transactions.py
  migrations/versions/   # 0001 schema, 0002 categories, 0003 dev user
  tests/                 # pytest (async); DB tests skip if no DB reachable
  .env                   # LOCAL secrets — gitignored, never commit
  .env.example           # template, fake placeholders only
docs/                    # FROZEN specs (see below)
```

## Environment / running (Windows)

- Python venv lives at `backend/.venv`. Run tools via the venv interpreter:
  `cd backend; .\.venv\Scripts\python.exe -m <pytest|alembic|uvicorn>`
- **Database = Neon by default; Docker is optional.** `DATABASE_URL` lives in
  `backend/.env`. A raw Neon dashboard URL works as-is — `app/config.normalize_async_dsn`
  forces `+asyncpg`, translates `sslmode`, drops `channel_binding`, adds
  `ssl=require` for remote hosts. Optional local Docker: `docker compose up -d`.
- Migrate + seed: `python -m alembic upgrade head`
- Test: `python -m pytest`  (currently the full suite passes; DB-backed tests
  SKIP when no DB is reachable, never because Docker is missing.)

## Secrets — hard rules

- NEVER commit `backend/.env` or any real secret. It is gitignored
  (`.gitignore`: `.env`, `*.env`, `backend/.env`, with `!.env.example`).
- NEVER print the Neon URL/password or `DEV_BEARER_TOKEN` back to the user.
- `.env.example` carries fake placeholders only.
- Before committing, confirm `backend/.env` is untracked and scan staged files
  for secrets.

## Auth & ownership model (API_CONTRACT §3)

- Single dev principal. Client sends `Authorization: Bearer <DEV_BEARER_TOKEN>`;
  `app/auth.require_principal` resolves it to `settings.dev_user_id` (a fixed
  sentinel seeded by migration `0003`). **`user_id` is server-resolved ONLY —
  never read/trusted from the client** (body or query).
- Missing/invalid token → `401 unauthorized` (generic envelope).
- Ownership mismatch is reported as **404 `not_found`, never 403** — identical to
  a missing row, so existence never leaks. A malformed UUID also → 404.

## Conventions

- **Money:** stored as signed integer agorot in `amount_minor` (bigint). Parse
  with `app/money.parse_amount_to_minor` (Decimal only, never float). Expense →
  negative. ≤2 decimals; `>2 → too_many_decimals`, `0 → zero_amount`,
  `negative → negative_amount` (all 422).
- **Timestamps:** RFC 3339 UTC with `Z` (seconds). Financial dates: `YYYY-MM-DD`.
- **Error envelope:** `{ "error": { code, message, request_id, field_errors? } }`.
  Raise `AppError(code=...)`; handlers in `app/errors.py` map code→HTTP+message.
- **Privacy logging:** use `log_event` with allow-listed keys only (request_id,
  endpoint, status, duration_bucket, row_count, opaque uuids, enums). NEVER log
  amount, note, raw input, merchant text, email, or tokens.
- **asyncpg gotcha:** bind `date`/`datetime`/`uuid` params as native Python
  objects (not strings) under casts; the driver rejects bare strings for those.
- **Tests:** use a fresh ephemeral principal per test (override `DEV_BEARER_TOKEN`
  + `DEV_USER_ID` via env, `get_settings.cache_clear()`) for isolation, and the
  autouse `_fresh_global_engine` fixture (the global engine is per-event-loop).

## Implemented endpoints (all under `/api/v1`, all auth-required except health)

- `GET /health`
- `GET /categories` — 22 seeded system categories
- `POST /transactions/quick-add` — amount-only manual create (201)
- `GET /transactions` — list; `month`/`category_id`/`uncategorized` filters;
  keyset cursor (`occurred_on,created_at,id` DESC); `{items, next_cursor}`
- `GET /transactions/{id}` — single read (404 if missing/non-owned)
- `DELETE /transactions/{id}` — hard delete, 204 (404 if missing/non-owned)

NOT yet implemented: `PATCH /transactions/{id}`, merchant resolution/aliases,
category rules, recurring templates, Home, UI, production auth.

## Frozen docs (do NOT change without explicit instruction)

`docs/`: `API_CONTRACT_V0_0_1.md`, `DATABASE_SCHEMA_V0_0_1.md`,
`CATEGORY_TAXONOMY.md`, `QA_TEST_PLAN_V0_0_1.md`, plus PRD/plan/import specs.
Match these field-for-field. If implementation conflicts with a frozen doc,
STOP and report the exact conflicting sections instead of guessing.

## Working style for this repo

- Build in small, committed slices. Per slice: confirm clean tree + remote in
  sync, run `alembic upgrade head` + `pytest` (must be green), implement, add
  tests, re-run, then commit/push only when the user asks.
- Commit messages end with a `Co-Authored-By` trailer.
- Do not implement endpoints/features outside the requested slice scope.

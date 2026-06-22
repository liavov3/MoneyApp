# Money App — Backend (v0.0.1, manual-first) — Foundation Slice

FastAPI + SQLAlchemy 2.x (async) + Alembic + PostgreSQL (pgvector installed,
unused). This is the **foundation slice only**: project skeleton, the standard
error envelope, DB connection, migrations for the 7 active tables (plus the two
deferred FK targets), the 22-category seed, and `GET /api/v1/health`. No feature
endpoints yet.

Built against the frozen specs in `../docs/`:
`DATABASE_SCHEMA_V0_0_1.md`, `API_CONTRACT_V0_0_1.md`, `CATEGORY_TAXONOMY.md`,
`QA_TEST_PLAN_V0_0_1.md`.

## Layout

```
backend/
  app/
    __init__.py
    config.py          # settings; DATABASE_URL externalized + asyncpg DSN normalization
    db.py              # async engine / session
    errors.py          # standard error envelope + exception handlers (API_CONTRACT §5)
    logging_utils.py   # privacy-safe logging (allow-list; duration buckets)
    middleware.py      # request_id + safe access log
    models.py          # SQLAlchemy models = Alembic metadata target
    seed_data.py       # canonical 22 categories
    main.py            # FastAPI app, mounted at /api/v1
    routers/
      health.py        # GET /api/v1/health
  migrations/
    env.py
    versions/
      0001_initial_schema.py     # tables + constraints + indexes + extensions
      0002_seed_categories.py    # 22 system categories (data migration)
  tests/
    conftest.py        # DB-availability gate (skips DB tests if no usable DB URL)
    test_app_boot.py   # no-DB: boot, error envelope, safe logging
    test_seed_categories.py
    test_constraints.py
    test_migrations.py
  alembic.ini
  docker-compose.yml   # OPTIONAL local Postgres + pgvector
  requirements.txt / requirements-dev.txt / pyproject.toml
  .env.example
```

## Setup

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Git Bash / macOS / Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then set DATABASE_URL (see below)
```

## Database — Neon is the default (Docker is optional)

Development and tests run against **Neon** (or any managed Postgres). Docker is
**not required** — it's just one optional way to provide a `DATABASE_URL`.

**Neon (default path):** create a Neon project, copy its connection string into
`backend/.env` as `DATABASE_URL`. A raw dashboard URL works as-is — the app
normalizes it for the asyncpg driver (forces `+asyncpg`, translates
`sslmode`, drops the unsupported `channel_binding`, and adds `ssl=require` for
remote hosts). Use a **non-production** database/branch. Neon ships the
`vector` extension, so the pgvector migration applies unchanged.

```
DATABASE_URL=postgresql://USER:PASSWORD@EP-xxxx.REGION.aws.neon.tech/neondb?sslmode=require
```

Optionally set `TEST_DATABASE_URL` (a separate Neon **branch**) so the test
suite's writes never touch your development data. If unset, tests fall back to
`DATABASE_URL`.

**Docker (optional path):** to use a local Postgres + pgvector instead:

```bash
cd backend
docker compose up -d        # waits until healthy
# then set in .env:
# DATABASE_URL=postgresql+asyncpg://money:money@localhost:5432/money_app
```

## Migrate + seed

```bash
cd backend
python -m alembic upgrade head   # creates 7 active + 2 deferred tables, seeds 22 categories
```

## Run the server

```bash
cd backend
uvicorn app.main:app --reload
# GET http://127.0.0.1:8000/api/v1/health  -> 200 {"status":"ok","db":"reachable"}
#   (503 backend_unavailable if the DB is down)
```

## Tests

```bash
cd backend
python -m pytest
```

DB-backed tests **skip** automatically only when no usable database URL is
reachable (never because Docker is missing), so the no-DB tests (app boot, error
envelope, privacy-safe logging) always run. With `DATABASE_URL` (or
`TEST_DATABASE_URL`) pointing at a reachable, migrated Neon database, the full
suite runs (seed counts, constraint rejections, migration head). Test DB
resolution order: `TEST_DATABASE_URL` → `DATABASE_URL`.

## Privacy / logging

`app/logging_utils.log_event` accepts only an allow-list of safe keys
(request id, endpoint, status, duration bucket, validation error code,
confidence level, enum names, opaque uuids, counts). Any other key is dropped
with a generic warning — never merchant text, amount, note, raw input,
correction content, email, or tokens.

## Auth (dev/local, server-resolved)

`GET /api/v1/categories` requires auth. v0.0.1 is single-user/dev: the client
sends `Authorization: Bearer <DEV_BEARER_TOKEN>`; the server resolves it to the
single dev principal (`app/auth.py`). `user_id` is **server-resolved only** —
never accepted from the client (API_CONTRACT §3). Missing/invalid token →
`401 unauthorized` standard envelope. Set `DEV_BEARER_TOKEN` in `.env`
(`.env.example` ships a fake placeholder only). The token is never logged.

## Scope guardrails

- Implemented: `GET /api/v1/health`, `GET /api/v1/categories` (auth-required).
- No Quick Add, transaction/merchant/rule/recurring, or Home endpoints yet.
- `accounts` / `import_batches` exist solely as FK targets; no routes expose them.
- pgvector is installed; **zero** vector tables/rows are created.

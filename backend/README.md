# MoneySaver backend

FastAPI + SQLAlchemy 2.x (async) + Alembic + PostgreSQL. The app includes manual
transactions, merchants, categories, recurring projections, monthly goals,
and private owner authentication. See [the deployment guide](../docs/PRIVATE_DEPLOYMENT.md)
for the free iPhone web installation and [the auth revision](../docs/PRIVATE_AUTH_V0_0_2.md)
for login, session cookies, native bearer sessions, CSRF, and provisioning.

Private login is the default. Run `python -m app.owner_setup` locally to choose
the first owner's username/password, or `python -m app.manage_auth --reset` to
replace a password and revoke all sessions. The deployed API has no registration
or setup endpoint. `ALLOW_DEV_BEARER=true` is restricted to local/test tooling;
production startup refuses it. Existing financial resource contracts are unchanged.

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

## Authentication

All financial resources require the server-resolved owner. Web clients use
HttpOnly cookies; native clients use revocable bearer sessions issued by
`POST /api/v1/auth/login`. Missing/invalid credentials return the standard 401
envelope. No resource accepts a client-supplied user ID. The old static token
works only when explicitly enabled for local/test tools, never in production.

## Scope guardrails

- Financial resource contracts remain governed by the frozen v0.0.1 documents;
  private authentication is the separately authorized v0.0.2 addition.
- `accounts` / `import_batches` exist solely as FK targets; no routes expose them.
- pgvector is installed; **zero** vector tables/rows are created.

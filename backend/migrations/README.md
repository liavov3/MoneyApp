# Alembic migrations

The DSN is read from `DATABASE_URL` (see `app/config.py` and `.env.example`),
never from `alembic.ini`.

Migration chain (apply with `alembic upgrade head`):

1. `0001_initial_schema` — pgcrypto + pgvector extensions (zero vectors),
   the 7 active tables, the 2 deferred FK-target tables (`accounts`,
   `import_batches`), and every constraint/index from
   `docs/DATABASE_SCHEMA_V0_0_1.md`.
2. `0002_seed_categories` — the 22 system categories (data migration,
   idempotent on re-run via key check).

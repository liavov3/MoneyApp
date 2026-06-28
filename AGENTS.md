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
    merchants.py     # merchant text normalization (MERCHANT_NORMALIZATION_SPEC §4)
    category_rules.py# §9 category-suggestion ladder (rules > recent-memory > default)
    auth.py          # server-resolved dev principal (Bearer token -> user_id)
    seed_data.py     # canonical 22 categories
    main.py          # FastAPI app, mounted at /api/v1
    routers/         # health.py, categories.py, merchants.py, transactions.py
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
- **Merchant matching (MERCHANT_NORMALIZATION_SPEC §4/§7):** normalize via
  `app/merchants.normalize_merchant_name`; auto-select ONLY at exact /
  normalized_exact / alias_exact (deterministic same-script + user-confirmed
  aliases) — never fuzzy, never silent cross-script merge. Merchant text, the
  normalized key, and rule `match_value` are sensitive — never logged/echoed.
- **Category suggestions (§9 ladder):** `app/category_rules.resolve_suggestion`
  resolves user_correction rules (merchant_exact > merchant_contains) >
  recent-merchant memory (last consumer category used) > merchant default >
  none. Rules are **update-not-stack** and **suggest-only** in Quick Add (never
  auto-applied to the saved row). bank_movement is never suggested.
- **Tests:** use a fresh ephemeral principal per test (override `DEV_BEARER_TOKEN`
  + `DEV_USER_ID` via env, `get_settings.cache_clear()`) for isolation, and the
  autouse `_fresh_global_engine` fixture (the global engine is per-event-loop).

## Implemented endpoints (all under `/api/v1`, all auth-required except health)

- `GET /health`
- `GET /categories` — 22 seeded system categories
- `POST /transactions/quick-add` — manual create (201); `amount` (required) +
  optional `category_id` (consumer-layer) + `merchant_input` (normalized,
  match-or-create). Returns `category_suggestion` from the §9 ladder
  (suggest-only). merchant `merchant_id`/recent-chip path still deferred.
- `GET /transactions` — list; `month`/`category_id`/`uncategorized` filters;
  keyset cursor (`occurred_on,created_at,id` DESC); `{items, next_cursor}`
- `GET /transactions/{id}` — single read (404 if missing/non-owned)
- `PATCH /transactions/{id}` — partial edit (amount/transaction_type/
  occurred_on/note/category_id; `category_id:null` clears)
- `DELETE /transactions/{id}` — hard delete, 204 (404 if missing/non-owned)
- `POST /transactions/{id}/categorize` — set category + optional
  `promote_to_rule` (UPSERT category_rules, update-not-stack,
  `source=user_correction`); `apply_to_existing` (default false) bulk-recategorizes
  the principal's other txns for that merchant. `match_value` never echoed.
- `GET /merchants/recent` — recent chips (`updated_at DESC`, limit 8/max 20),
  `suggested_category_*` via the §9 ladder
- `GET /merchants/suggestions?query=` — typed autocomplete + confidence ladder
  (exact/normalized_exact/alias_exact auto-select; recent_suggestion/contains
  suggest); per-item `suggested_category_*` via the §9 ladder
- `POST /merchants/{id}/aliases` — user-confirmed alias (only cross-script link
  path); optional `absorb_merchant_id` re-points txns + deletes the duplicate;
  key already pointing elsewhere → 409

Category-rule suggestions are wired into quick-add, `/merchants/recent`, and
`/merchants/suggestions` via the §9 ladder (incl. recent-merchant memory).

NOT yet implemented: `GET /home` (dashboard), `rule_prompt.offer` in quick-add
("Always categorize…?"), `POST /category-rules` + `PATCH/DELETE /category-rules`,
recurring templates, bank/card import, UI/mobile, production auth.

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

## Tooling, agents & skill policy (MoneyApp)

**Every future implementation prompt MUST include a "Recommended skill/tooling"
line AND why those tools fit this slice.** No plugin/MCP/skill/agent is used
just because it exists — a narrow reliable toolchain, not plugin sprawl. Keep
endpoint slices small. Contract + money + privacy checks are MANDATORY on every
backend slice — see the `moneyapp-contract-guard` skill.

### Agents (`.claude/agents/`)
Build / lead:
- `backend-api-engineer` — leads focused FastAPI endpoint implementation.
- `database-engineer` — migrations, constraints, indexes, Neon/Postgres issues.
- `qa-tester` — regression + contract tests (only when code actually changed).

Review guardians (read-only; run before claiming a slice done):
- `api-contract-guardian` — response/status/error shapes vs `API_CONTRACT_V0_0_1.md`.
- `money-invariants-guardian` — Decimal-only parse, signed agorot, no rounding,
  `amount_minor` rules.
- `privacy-security-auditor` — server-resolved `user_id`, ownership-as-404,
  generic errors, no PII/secrets in logs.

### Skill
- `moneyapp-contract-guard` (`.claude/skills/`) — invariants checklist; invoke
  before starting and before claiming done any backend slice.

### Ponytail (installed, active)
Use for: keeping slices minimal, and `/ponytail-review` / `/ponytail-audit` to
catch over-engineering or a quick contract/structure consistency pass. NOT for:
money, contract, or privacy correctness — those belong to the guardians, and
Ponytail explicitly never simplifies away validation/security. Do not auto-invoke.

### MCP / external tools (documented policy — none auto-installed; report before installing)
- **security-guidance plugin** — backend / security-sensitive code review.
- **Context7 MCP** — only when touching external library APIs (FastAPI,
  Pydantic, SQLAlchemy, Alembic, Expo, React Native, TanStack Query).
- **GitHub MCP** — only for issue / PR summaries / review workflows.
- **Neon MCP** — dev/test branch inspection or READ-ONLY checks only; never
  production, never destructive actions without explicit approval.
- **Maestro / EAS** — later, when mobile app work begins.

### Hook
- `scripts/git-hooks/pre-commit` (install: `cp scripts/git-hooks/pre-commit
  .git/hooks/pre-commit`) — blocks staging a real `.env`, blocks a staged Neon
  URL / `npg_` password / live `DEV_BEARER_TOKEN`, and reminds to run pytest.
  Non-destructive (only rejects the commit with a message); never logs the secret.

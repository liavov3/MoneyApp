"""Pytest fixtures.

DB-backed tests are SKIPPED (not failed) only when no usable database URL is
reachable — never because Docker is absent. The default development/testing
target is Neon (or any managed Postgres): set `DATABASE_URL` (and optionally a
dedicated `TEST_DATABASE_URL`) in `backend/.env` or the environment. A local
Docker Postgres is one optional way to provide that URL, not a requirement.

Resolution order for the DB used by tests:
  1. `TEST_DATABASE_URL` env var (dedicated test DB — recommended: a Neon branch)
  2. `DATABASE_URL` env var
  3. `test_database_url` from settings/`.env`
  4. `database_url` from settings/`.env`

All candidates are normalized for the asyncpg driver (so a DSN pasted from the
Neon dashboard works). Tests that boot the app without touching the DB always
run.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings, normalize_async_dsn

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _db_url() -> str:
    """Resolve the DSN the test suite should target (asyncpg-normalized).

    Prefers a dedicated test DB so test writes stay off the development DB.
    """
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if raw:
        return normalize_async_dsn(raw)
    settings = get_settings()
    return settings.async_test_database_url or settings.async_database_url


async def _db_reachable(url: str) -> bool:
    # Short connect timeout so an unset/unreachable URL skips fast instead of
    # blocking the no-DB suite on DNS/TCP waits.
    engine: AsyncEngine = create_async_engine(
        url, pool_pre_ping=True, connect_args={"timeout": 5}
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def db_available() -> bool:
    try:
        return asyncio.run(_db_reachable(_db_url()))
    except Exception:
        return False


@pytest.fixture(scope="session")
def require_db(db_available: bool) -> None:
    if not db_available:
        pytest.skip(
            "No usable database reachable — set TEST_DATABASE_URL or DATABASE_URL "
            "(Neon by default; Docker Postgres optional) and run "
            "`python -m alembic upgrade head`."
        )


@pytest.fixture(scope="session")
def migrated(require_db: None) -> None:
    """Apply Alembic migrations once for the DB-backed test session."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


@pytest_asyncio.fixture
async def engine(migrated: None) -> AsyncEngine:
    eng = create_async_engine(_db_url(), pool_pre_ping=True)
    yield eng
    await eng.dispose()

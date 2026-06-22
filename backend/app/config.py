"""Application configuration.

The database DSN is externalized via the `DATABASE_URL` environment variable
(or a local `.env` file). No secrets are hard-coded. See `.env.example`.

Neon (or any managed Postgres) is the default development/testing target; a
local Docker Postgres is optional. Connection strings copied from the Neon
dashboard use libpq-style query params (`sslmode`, `channel_binding`) and a
bare `postgresql://` scheme. The async driver this app uses (asyncpg) does NOT
understand those params, so `normalize_async_dsn` rewrites a pasted DSN into an
asyncpg-safe form (force `+asyncpg`, translate `sslmode` -> `ssl`, drop the
unsupported `channel_binding`, and default `ssl=require` for remote hosts).
This is connection plumbing only — it changes no schema, contract, or product
behavior.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# Hosts that are treated as local/plaintext (no implicit SSL requirement).
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}

# libpq sslmode values that asyncpg accepts directly as its `ssl` argument.
_SSL_STRINGS = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def normalize_async_dsn(raw: str) -> str:
    """Rewrite a Postgres DSN into a form the asyncpg driver accepts.

    Accepts a plain `postgresql://` / `postgres://` URL (e.g. copied straight
    from the Neon dashboard) and returns an asyncpg-safe SQLAlchemy URL:

    * driver forced to `postgresql+asyncpg`;
    * `channel_binding` removed (asyncpg has no such connect arg — it would
      raise `TypeError` at connect time);
    * `sslmode=<x>` translated to `ssl=<x>` (asyncpg's native SSL arg);
    * for non-local hosts with no SSL specified, `ssl=require` is added so
      Neon (which mandates TLS) connects without manual tweaking.

    Local/Docker URLs (localhost) are left plaintext, so the optional Docker
    path keeps working unchanged.
    """
    url = make_url(raw)

    drivername = url.drivername or "postgresql"
    if not drivername.startswith("postgresql+asyncpg"):
        # postgresql, postgres, postgresql+psycopg, postgresql+psycopg2 -> asyncpg
        url = url.set(drivername="postgresql+asyncpg")

    query = {k: v for k, v in url.query.items()}

    # asyncpg does not support channel binding negotiation via this kwarg.
    query.pop("channel_binding", None)

    # Translate libpq sslmode -> asyncpg `ssl` (only if ssl not already set).
    sslmode = query.pop("sslmode", None)
    if isinstance(sslmode, (list, tuple)):
        sslmode = sslmode[0] if sslmode else None
    if sslmode and "ssl" not in query:
        query["ssl"] = sslmode if sslmode in _SSL_STRINGS else "require"

    # Remote hosts (Neon, other managed PG) require TLS; default it on.
    host = (url.host or "").lower()
    if "ssl" not in query and host not in _LOCAL_HOSTS:
        query["ssl"] = "require"

    url = url.set(query=query)
    return url.render_as_string(hide_password=False)


class Settings(BaseSettings):
    """Runtime settings, loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Async DSN. Externalized — never hard-code real credentials. The default
    # is a harmless local fallback; the real value (Neon by default) comes from
    # `.env`. Raw value as provided; use `async_database_url` for connecting.
    database_url: str = "postgresql+asyncpg://money:money@localhost:5432/money_app"

    # Optional dedicated DSN for the test suite. When unset, tests fall back to
    # `database_url` (see tests/conftest.py). A separate Neon branch here keeps
    # test writes off the development database.
    test_database_url: str | None = None

    app_env: str = "local"
    log_level: str = "INFO"

    # Static dev bearer token (single-user v0.0.1). Presented by the client as
    # `Authorization: Bearer <token>` and resolved SERVER-SIDE to the single
    # dev principal (app/auth.py). Held in config/secrets only — never in the
    # repo or the mobile bundle (API_CONTRACT §3). When unset, no principal can
    # be resolved and every authed request is 401.
    dev_bearer_token: str | None = None

    # The server-resolved user_id for the single dev/test principal. The client
    # NEVER supplies user_id (API_CONTRACT §3); it is resolved here, server-side.
    # Fixed sentinel so the principal is stable across processes. The matching
    # `users` row is seeded by the first user-owned-write slice; v0.0.1
    # categories are system rows (user_id IS NULL) and need no users row.
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"

    @property
    def async_database_url(self) -> str:
        """The application/migration DSN, normalized for the asyncpg driver."""
        return normalize_async_dsn(self.database_url)

    @property
    def async_test_database_url(self) -> str | None:
        """Normalized test DSN, or None when no dedicated test DB is configured."""
        if not self.test_database_url:
            return None
        return normalize_async_dsn(self.test_database_url)

    @property
    def sync_database_url(self) -> str:
        """A synchronous DSN form, useful for tooling that needs psycopg.

        Not required by the app (which is fully async) but handy for ad-hoc
        scripts. Uses the raw DSN so libpq-style params remain intact.
        """
        url = make_url(self.database_url)
        return url.set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""App boot + error-envelope tests that do NOT require a database.

Covers: (a) app boots; the error envelope shape (QA-11-01); health returns the
backend_unavailable envelope when the DB is down (QA-11-07 shape); and that the
privacy-safe logger refuses unsafe keys (QA-10 pattern).
"""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.logging_utils import _ALLOWED_KEYS, duration_bucket, log_event
from app.main import create_app


@pytest.mark.asyncio
async def test_app_boots_and_health_route_exists() -> None:
    # (a) app boots and the health route is registered under /api/v1.
    app = create_app()
    assert "/api/v1/health" in app.openapi()["paths"]


@pytest.mark.asyncio
async def test_health_returns_ok_when_db_reachable(monkeypatch) -> None:
    """Success path: a working SELECT 1 -> 200 {"status":"ok","db":"reachable"}.

    Uses a fake sessionmaker so this runs without a real Postgres.
    """
    import app.routers.health as health_mod

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, _stmt):
            return None

    monkeypatch.setattr(health_mod, "get_sessionmaker", lambda: (lambda: _FakeSession()))

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "reachable"}
    assert resp.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_health_returns_backend_unavailable_when_db_down(monkeypatch) -> None:
    """QA-11-07: DB unreachable -> 503 backend_unavailable, generic message."""
    import app.routers.health as health_mod

    class _BrokenSessionmaker:
        def __call__(self):  # noqa: D401
            raise RuntimeError("db down")

    monkeypatch.setattr(health_mod, "get_sessionmaker", lambda: _BrokenSessionmaker())

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 503
    body = resp.json()
    # QA-11-01: stable envelope shape.
    assert set(body["error"].keys()) >= {"code", "message", "request_id"}
    assert body["error"]["code"] == "backend_unavailable"
    # Generic, content-free message.
    assert "your entry was not saved" in body["error"]["message"]
    assert resp.headers.get("X-Request-ID")


def test_duration_bucket() -> None:
    assert duration_bucket(0.5) == "<2s"
    assert duration_bucket(3.0) == "2-5s"
    assert duration_bucket(9.0) == ">5s"


def test_logger_rejects_unsafe_keys(caplog) -> None:
    """QA-10 pattern: unsafe keys (e.g. merchant text/amount) are dropped."""
    with caplog.at_level(logging.WARNING, logger="money_app"):
        log_event(
            "test_event",
            request_id="req_test",
            endpoint="/x",
            status=200,
            merchant_input="Golda",  # unsafe — must be dropped
            amount_minor=-3300,  # unsafe — must be dropped
            note="secret",  # unsafe — must be dropped
        )
    joined = "\n".join(caplog.messages)
    assert "Golda" not in joined
    assert "secret" not in joined
    assert "-3300" not in joined
    assert "dropped_unsafe_log_keys" in joined
    # Sanity: the allow-list does not contain any obviously sensitive key.
    for forbidden in ("amount", "amount_minor", "note", "merchant_input", "email", "token"):
        assert forbidden not in _ALLOWED_KEYS

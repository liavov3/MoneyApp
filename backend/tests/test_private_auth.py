"""Real owner sessions, CSRF, throttling, revocation and financial isolation."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app import db as app_db
from app.auth import token_digest
from app.config import Settings, get_settings
from app.main import create_app
from app.manage_auth import provision_owner
from app.models import PrivateAccount, PrivateLoginWindow, PrivateSession, User
from app.private_passwords import hash_new_password

PASSWORD = "synthetic testing passphrase 4729"
WEB_HEADERS = {"Origin": "https://private.example", "X-MoneySaver-Client": "web"}


@pytest_asyncio.fixture
async def owner(engine, monkeypatch):
    user_id = str(uuid.uuid4())
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_DEV_BEARER", "false")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://private.example")
    monkeypatch.setenv("OWNER_USER_ID", user_id)
    monkeypatch.setenv("DEV_BEARER_TOKEN", "old-code-must-not-work")
    get_settings.cache_clear()
    await app_db.dispose_engine()
    async with engine.begin() as conn:
        await conn.execute(User.__table__.insert().values(id=user_id))
    await provision_owner("private.owner", PASSWORD)
    yield user_id
    await app_db.dispose_engine()
    async with engine.begin() as conn:
        await conn.execute(delete(User).where(User.id == user_id))
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(owner):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="https://private.example") as client:
        yield client


async def sign_in(client, *, native=False, password=PASSWORD, username="private.owner"):
    return await client.post("/api/v1/auth/login", headers={} if native else WEB_HEADERS,
                             json={"username": username, "password": password,
                                   "client": "native" if native else "web"})


@pytest.mark.asyncio
async def test_cookie_login_refresh_private_data_and_logout(client, engine, owner):
    assert (await client.get("/api/v1/transactions")).status_code == 401
    login = await sign_in(client)
    assert login.status_code == 200
    assert set(login.json()) == {"authenticated", "expires_at"}
    cookie = login.headers["set-cookie"]
    for flag in ["__Host-moneysaver_session=", "HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=2592000"]:
        assert flag in cookie
    assert "Domain=" not in cookie
    token = client.cookies.get("__Host-moneysaver_session")
    async with engine.connect() as conn:
        row = (await conn.execute(select(PrivateSession.__table__).where(PrivateSession.user_id == owner))).mappings().one()
        assert row["token_hash"] == token_digest(token)
        assert token not in str(dict(row))
        account = (await conn.execute(select(PrivateAccount.__table__).where(PrivateAccount.user_id == owner))).mappings().one()
        assert account["password_hash"].startswith("$argon2id$")
        assert PASSWORD not in str(dict(account))
    assert (await client.get("/api/v1/auth/session")).status_code == 200
    saved = await client.post("/api/v1/transactions/quick-add", headers=WEB_HEADERS, json={"amount": "12.34"})
    assert saved.status_code == 201
    assert saved.json()["transaction"]["amount_minor"] == -1234
    assert (await client.get("/api/v1/transactions")).json()["items"][0]["amount_minor"] == -1234
    assert (await client.post("/api/v1/auth/logout", headers=WEB_HEADERS)).status_code == 204
    assert (await client.get("/api/v1/transactions")).status_code == 401
    assert (await client.get("/api/v1/categories", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await client.post("/api/v1/auth/logout", headers=WEB_HEADERS)).status_code == 204


@pytest.mark.asyncio
async def test_native_login_and_owner_filter(client, engine, owner):
    response = await sign_in(client, native=True)
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/categories", headers=headers)).status_code == 200
    other_id = str(uuid.uuid4())
    other_token = "X" * 43
    async with engine.begin() as conn:
        await conn.execute(User.__table__.insert().values(id=other_id))
        await conn.execute(PrivateAccount.__table__.insert().values(user_id=other_id, username=other_id, password_hash="unused"))
        await conn.execute(PrivateSession.__table__.insert().values(user_id=other_id, token_hash=token_digest(other_token), expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    try:
        assert (await client.get("/api/v1/categories", headers={"Authorization": f"Bearer {other_token}"})).status_code == 401
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(User).where(User.id == other_id))
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/session", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_cross_site_login_native_bypass_and_cookie_writes_rejected(client):
    body = {"username": "private.owner", "password": PASSWORD, "client": "web"}
    for headers in [{}, {"Origin": "https://evil.example", "X-MoneySaver-Client": "web"}, {"Origin": "https://private.example"}]:
        assert (await client.post("/api/v1/auth/login", headers=headers, json=body)).status_code == 403
    assert (await client.post("/api/v1/auth/login", headers=WEB_HEADERS, json={**body, "client": "native"})).status_code == 403
    assert (await sign_in(client)).status_code == 200
    for headers in [{}, {"Origin": "https://evil.example", "X-MoneySaver-Client": "web"}, {"Origin": "null", "X-MoneySaver-Client": "web"}]:
        assert (await client.post("/api/v1/transactions/quick-add", headers=headers, json={"amount": "1.00"})).status_code == 403
        assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/transactions")).json()["items"] == []
    # A malformed bearer cannot downgrade into valid cookie authentication.
    assert (await client.get("/api/v1/categories", headers={"Authorization": "not-bearer"})).status_code == 401


@pytest.mark.asyncio
async def test_wrong_credentials_generic_and_rate_limit_survives_new_app(client, owner, engine):
    for i in range(5):
        result = await sign_in(client, password="wrong password", username="unknown.user" if i % 2 else "private.owner")
        assert result.status_code == 401
        assert result.json()["error"]["code"] == "unauthorized"
        assert "wrong password" not in result.text and "private.owner" not in result.text
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="https://private.example") as fresh:
        limited = await sign_in(fresh)
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "60"
    async with engine.begin() as conn:
        await conn.execute(update(PrivateLoginWindow).where(PrivateLoginWindow.user_id == owner).values(window_started_at=datetime.now(timezone.utc) - timedelta(seconds=61)))
    assert (await sign_in(client)).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_attempts_cannot_exceed_limit(client):
    results = await asyncio.gather(*(sign_in(client, native=True, password="wrong password") for _ in range(9)))
    assert sorted(result.status_code for result in results) == [401] * 5 + [429] * 4


@pytest.mark.asyncio
async def test_expiry_reset_and_relogin_revoke_old_sessions(client, engine, owner):
    first = (await sign_in(client, native=True)).json()["access_token"]
    async with engine.begin() as conn:
        await conn.execute(update(PrivateSession).where(PrivateSession.user_id == owner).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    assert (await client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {first}"})).status_code == 401
    second = (await sign_in(client, native=True)).json()["access_token"]
    new_password = "a different synthetic passphrase 8836"
    await provision_owner("private.owner", new_password, reset=True)
    assert (await client.get("/api/v1/categories", headers={"Authorization": f"Bearer {second}"})).status_code == 401
    assert (await sign_in(client)).status_code == 401
    assert (await sign_in(client, password=new_password)).status_code == 200
    old_cookie = client.cookies.get("__Host-moneysaver_session")
    assert (await sign_in(client, password=new_password)).status_code == 200
    assert client.cookies.get("__Host-moneysaver_session") != old_cookie
    assert (await client.get("/api/v1/categories", headers={"Authorization": f"Bearer {old_cookie}"})).status_code == 401


@pytest.mark.asyncio
async def test_production_disables_old_code_signup_docs_and_sensitive_cache(client):
    assert (await client.get("/api/v1/categories", headers={"Authorization": "Bearer old-code-must-not-work"})).status_code == 401
    for path in ["/api/v1/auth/register", "/api/v1/auth/setup", "/docs", "/openapi.json"]:
        assert (await client.get(path)).status_code == 404
    result = await client.get("/api/v1/categories")
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["referrer-policy"] == "no-referrer"
    assert result.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in result.headers["content-security-policy"]
    assert "access-control-allow-origin" not in result.headers


@pytest.mark.asyncio
async def test_login_validation_and_logs_never_echo_credentials(client, caplog):
    with caplog.at_level(logging.INFO, logger="money_app"):
        malformed = await client.post("/api/v1/auth/login", headers=WEB_HEADERS, json={
            "username": "private.owner", "password": PASSWORD, "client": "web", "user_id": "sensitive-input",
        })
        assert malformed.status_code == 422
        await sign_in(client, password="wrong synthetic password")
    combined = malformed.text + caplog.text
    for secret in [PASSWORD, "private.owner", "wrong synthetic password", "sensitive-input"]:
        assert secret not in combined


@pytest.mark.parametrize("origin", [None, "http://public.example", "https://user:pass@example.com", "https://example.com/path", "https://example.com?key=value"])
def test_production_requires_valid_https_origin(origin):
    settings = Settings(_env_file=None, app_env="production", public_origin=origin, render_external_hostname=None)
    with pytest.raises(RuntimeError):
        settings.validate_deployment()


def test_production_refuses_dev_override():
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, app_env="production", public_origin="https://private.example", allow_dev_bearer=True).validate_deployment()


def test_weak_provisioning_password_refused():
    with pytest.raises(ValueError):
        hash_new_password("too short")

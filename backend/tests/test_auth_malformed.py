"""Malformed bearer bytes must fail as unauthorized, never as a server error."""
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app import auth
from app.errors import AppError


@pytest.mark.parametrize("header", [b"Bearer \xff", b"Bearer \xc3\xa9", b"Bearer wrong", b"Bearer "])
@pytest.mark.asyncio
async def test_malformed_or_wrong_bearer_is_unauthorized(monkeypatch, header):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(dev_bearer_token="synthetic-token", dev_user_id="user", allow_dev_bearer=True, production=False))
    request = Request({"type": "http", "headers": [(b"authorization", header)]})
    with pytest.raises(AppError) as caught:
        await auth.require_principal(request, None)
    assert caught.value.code == "unauthorized"


@pytest.mark.asyncio
async def test_valid_bearer_still_resolves_only_server_principal(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(dev_bearer_token="synthetic-token", dev_user_id="server-user", allow_dev_bearer=True, production=False))
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer synthetic-token")]})
    assert (await auth.require_principal(request, None)).user_id == "server-user"

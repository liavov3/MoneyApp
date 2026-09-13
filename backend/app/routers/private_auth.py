"""Private login, session restoration, and logout; no public registration."""
from datetime import datetime, timedelta, timezone
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth import (SESSION_SECONDS, Principal, cookie_name, presented_session,
                      require_browser_origin, require_principal, token_digest)
from app.config import get_settings
from app.db import get_session
from app.errors import AppError
from app.models import PrivateAccount, PrivateLoginWindow, PrivateSession
from app.private_passwords import dummy_hash, normalize_username, password_hasher

router = APIRouter(prefix="/auth")


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=128, repr=False)
    client: Literal["web", "native"]

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        return normalize_username(value)


class SessionOutput(BaseModel):
    authenticated: Literal[True] = True
    expires_at: datetime


class LoginOutput(SessionOutput):
    access_token: str | None = None


async def reserve_login_attempt(db: AsyncSession, user_id: str) -> None:
    now = datetime.now(timezone.utc)
    expired = PrivateLoginWindow.window_started_at <= now - timedelta(seconds=60)
    statement = insert(PrivateLoginWindow).values(
        user_id=user_id, window_started_at=now, attempts=1,
    ).on_conflict_do_update(
        index_elements=[PrivateLoginWindow.user_id],
        set_={
            "window_started_at": case((expired, now), else_=PrivateLoginWindow.window_started_at),
            "attempts": case((expired, 1), else_=PrivateLoginWindow.attempts + 1),
        },
        where=or_(expired, PrivateLoginWindow.attempts < 5),
    ).returning(PrivateLoginWindow.attempts)
    attempt = await db.scalar(statement)
    # Commit the reservation even if password verification subsequently fails.
    await db.commit()
    if attempt is None:
        raise AppError(code="rate_limited")


@router.post("/login", response_model=LoginOutput, response_model_exclude_none=True)
async def login(body: LoginInput, request: Request, response: Response,
                db: AsyncSession = Depends(get_session)):
    if body.client == "web":
        require_browser_origin(request)
    elif "origin" in request.headers:
        raise AppError(code="unsupported_operation")
    settings = get_settings()
    try:
        await reserve_login_attempt(db, settings.owner_user_id)
        account = await db.scalar(select(PrivateAccount).where(
            PrivateAccount.user_id == settings.owner_user_id,
        ).with_for_update())
        known = account is not None and secrets.compare_digest(
            account.username.encode(), body.username.encode(),
        )
        encoded = account.password_hash if known else dummy_hash
        valid = await run_in_threadpool(password_hasher.verify, body.password, encoded)
        if not known or not valid:
            raise AppError(code="unauthorized")
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=SESSION_SECONDS)
        await db.execute(delete(PrivateSession).where(
            PrivateSession.user_id == settings.owner_user_id,
            PrivateSession.expires_at <= now,
        ))
        # A browser re-login replaces its previous session, preventing fixation
        # and orphaned sessions if a successful login response was interrupted.
        old_token = request.cookies.get(cookie_name()) if body.client == "web" else None
        if old_token:
            await db.execute(delete(PrivateSession).where(
                PrivateSession.user_id == settings.owner_user_id,
                PrivateSession.token_hash == token_digest(old_token),
            ))
        token = secrets.token_urlsafe(32)
        db.add(PrivateSession(token_hash=token_digest(token),
                              user_id=settings.owner_user_id, expires_at=expires_at))
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise AppError(code="backend_unavailable") from None
    if body.client == "web":
        response.set_cookie(cookie_name(), token, max_age=SESSION_SECONDS,
                            secure=settings.production, httponly=True,
                            samesite="strict", path="/")
    return LoginOutput(expires_at=expires_at,
                       access_token=token if body.client == "native" else None)


@router.get("/session", response_model=SessionOutput)
async def current_session(principal: Principal = Depends(require_principal)):
    if principal.expires_at is None:
        raise AppError(code="unauthorized")
    return SessionOutput(expires_at=principal.expires_at)


@router.post("/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_session)):
    token = presented_session(request)
    try:
        if token:
            await db.execute(delete(PrivateSession).where(
                PrivateSession.token_hash == token_digest(token),
                PrivateSession.user_id == get_settings().owner_user_id,
            ))
            await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise AppError(code="backend_unavailable") from None
    response = Response(status_code=204)
    response.delete_cookie(cookie_name(), path="/", secure=get_settings().production,
                           httponly=True, samesite="strict")
    return response

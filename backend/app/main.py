"""FastAPI application factory — Money App backend v0.0.1 (foundation slice).

Mounts the API under /api/v1. Implemented so far: GET /api/v1/health,
GET /api/v1/categories, POST /api/v1/transactions/quick-add (amount-only
subset), GET /api/v1/transactions (list), and GET /api/v1/transactions/{id}
(single read), and DELETE /api/v1/transactions/{id} (hard delete) — all
auth-required with a server-resolved principal. Remaining feature endpoints
(merchant matching, categorize, home, recurring, PATCH edit) are intentionally
NOT implemented yet.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import dispose_engine
from app.errors import register_exception_handlers
from app.logging_utils import configure_logging
from app.middleware import RequestContextMiddleware
from app.routers import (
    categories,
    health,
    home,
    merchants,
    monthly_goals,
    recurring,
    transactions,
)

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Money App API",
        version="0.0.1",
        description="Manual-first personal finance backend (foundation slice).",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router, prefix=API_V1_PREFIX, tags=["health"])
    app.include_router(categories.router, prefix=API_V1_PREFIX, tags=["categories"])
    app.include_router(merchants.router, prefix=API_V1_PREFIX, tags=["merchants"])
    app.include_router(transactions.router, prefix=API_V1_PREFIX, tags=["transactions"])
    app.include_router(home.router, prefix=API_V1_PREFIX, tags=["home"])
    app.include_router(recurring.router, prefix=API_V1_PREFIX, tags=["recurring"])
    app.include_router(
        monthly_goals.router, prefix=API_V1_PREFIX, tags=["monthly-goals"]
    )

    return app


app = create_app()

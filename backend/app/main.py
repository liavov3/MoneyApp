"""MoneySaver API and optional same-origin static web application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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
    private_auth,
    transactions,
)

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_deployment()
    configure_logging(settings.log_level)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Money App API",
        version="0.0.1",
        description="Manual-first personal finance with private owner sessions.",
        lifespan=lifespan,
        docs_url=None if settings.production else "/docs",
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router, prefix=API_V1_PREFIX, tags=["health"])
    app.include_router(private_auth.router, prefix=API_V1_PREFIX, tags=["auth"])
    app.include_router(categories.router, prefix=API_V1_PREFIX, tags=["categories"])
    app.include_router(merchants.router, prefix=API_V1_PREFIX, tags=["merchants"])
    app.include_router(transactions.router, prefix=API_V1_PREFIX, tags=["transactions"])
    app.include_router(home.router, prefix=API_V1_PREFIX, tags=["home"])
    app.include_router(recurring.router, prefix=API_V1_PREFIX, tags=["recurring"])
    app.include_router(
        monthly_goals.router, prefix=API_V1_PREFIX, tags=["monthly-goals"]
    )

    if settings.web_dist_dir:
        app.mount("/", StaticFiles(directory=settings.web_dist_dir, html=True), name="web")
    return app


app = create_app()

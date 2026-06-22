"""Standard error envelope and exception handlers (API_CONTRACT §5).

Every non-2xx response uses the shape:
    { "error": { "code", "message", "request_id", "field_errors"? } }

`code` is a stable machine-readable enum; `message` is generic and content-free
(never leaks merchant text, amounts, notes, or correction content). A
`request_id` (also used in safe logs) is attached to every request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_utils import log_event

# code -> HTTP status (API_CONTRACT §5 table). Integer literals avoid a
# Starlette deprecation alias and pin the contract's status codes explicitly.
ERROR_STATUS: dict[str, int] = {
    "validation_error": 422,
    "not_found": 404,
    "conflict": 409,
    "unauthorized": 401,
    "unsupported_operation": 403,
    "backend_unavailable": 503,
    "internal_error": 500,
}

# Generic, content-free messages.
ERROR_MESSAGE: dict[str, str] = {
    "validation_error": "One or more fields are invalid.",
    "not_found": "Resource not found.",
    "conflict": "This conflicts with existing data.",
    "unauthorized": "Authentication required.",
    "unsupported_operation": "This operation is not supported.",
    "backend_unavailable": (
        "Service temporarily unavailable — your entry was not saved. Try again."
    ),
    "internal_error": "Something went wrong. Try again.",
}


@dataclass
class AppError(Exception):
    """Raise this anywhere to produce the standard envelope."""

    code: str
    field_errors: list[dict[str, str]] | None = None
    message: str | None = None

    def http_status(self) -> int:
        return ERROR_STATUS.get(self.code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def safe_message(self) -> str:
        return self.message or ERROR_MESSAGE.get(self.code, ERROR_MESSAGE["internal_error"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")


def build_envelope(
    code: str,
    request_id: str,
    *,
    message: str | None = None,
    field_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message or ERROR_MESSAGE.get(code, ERROR_MESSAGE["internal_error"]),
        "request_id": request_id,
    }
    if field_errors is not None:
        error["field_errors"] = field_errors
    return {"error": error}


def _json_error(
    request: Request,
    code: str,
    *,
    message: str | None = None,
    field_errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    http_status = ERROR_STATUS.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    # Privacy-safe log: code/status/request_id only — never the bad value.
    log_event(
        "request_error",
        level=logging.WARNING if http_status < 500 else logging.ERROR,
        request_id=request_id,
        endpoint=request.url.path,
        method=request.method,
        status=http_status,
        validation_error_code=code,
    )
    return JSONResponse(
        status_code=http_status,
        content=build_envelope(
            code, request_id, message=message, field_errors=field_errors
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _json_error(
            request,
            exc.code,
            message=exc.safe_message(),
            field_errors=exc.field_errors,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Map FastAPI/Pydantic errors to field codes WITHOUT echoing the bad
        # input value (privacy: never log/return the offending content).
        field_errors: list[dict[str, str]] = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            field = loc[-1] if loc else "body"
            field_errors.append(
                {
                    "field": field,
                    "code": _map_pydantic_code(err.get("type", "invalid")),
                    "message": "This field is invalid.",
                }
            )
        return _json_error(request, "validation_error", field_errors=field_errors)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _status_to_code(exc.status_code)
        return _json_error(request, code)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Never leak a stack trace or content (QA-10-10 / QA-11-08).
        return _json_error(request, "internal_error")


def _map_pydantic_code(pydantic_type: str) -> str:
    mapping = {
        "missing": "missing",
        "value_error": "invalid_value",
        "string_too_short": "too_short",
        "int_parsing": "not_a_number",
        "float_parsing": "not_a_number",
        "decimal_parsing": "not_a_number",
    }
    return mapping.get(pydantic_type, "invalid")


def _status_to_code(http_status: int) -> str:
    for code, st in ERROR_STATUS.items():
        if st == http_status:
            return code
    if http_status == status.HTTP_405_METHOD_NOT_ALLOWED:
        return "unsupported_operation"
    return "internal_error"

"""One error envelope for the whole API, plus exception handlers.

Every error response has the same shape, so the existing frontend can branch
on machine-readable codes instead of parsing prose:

    { "error": { "code": "SLOT_TAKEN", "message": "...", "request_id": "..." } }

Postgres SQLSTATE mapping (the asyncpg layer never leaks raw driver errors):
    23P01 exclusion violation  -> 409 SLOT_TAKEN       (someone booked first)
    23505  unique violation    -> 409 DUPLICATE        (idempotency race)
    23503  FK violation        -> 409 REFERENT_MISSING
    08***  connection classes  -> 503 DATABASE_UNAVAILABLE (safe to retry)
    57014  statement timeout   -> 503 QUERY_TIMEOUT
"""

from __future__ import annotations

import json
import traceback
import uuid

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Raise anywhere in a handler; becomes a structured error response."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def log_event(event: str, **fields) -> None:
    """Structured log line; lands in Workers Logs (observability)."""
    try:
        line = json.dumps({"event": event, **fields}, default=str, separators=(",", ":"))
    except Exception:
        line = f"event={event}"
    print(line, flush=True)


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _payload(code: str, message: str, request_id: str, details: dict | None = None, fields: list | None = None) -> dict:
    err: dict = {"code": code, "message": message, "request_id": request_id}
    if details:
        err["details"] = details
    if fields is not None:
        err["fields"] = fields
    return {"error": err}


_SQLSTATE = {
    "23P01": (409, "SLOT_TAKEN", "That time slot was just taken by someone else. Please pick another slot."),
    "23505": (409, "DUPLICATE", "The record already exists."),
    "23503": (409, "REFERENT_MISSING", "The referenced barber or service no longer exists."),
    "40001": (503, "RETRY_LATER", "The database asked to retry; it is safe to retry this request."),
    "40P01": (503, "RETRY_LATER", "Database deadlock; it is safe to retry this request."),
    "57014": (503, "QUERY_TIMEOUT", "The database query timed out; safe to retry."),
    "55P03": (503, "QUERY_TIMEOUT", "The database could not lock the required rows in time."),
}

_HTTP_CODE_MAP = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        rid = _request_id()
        if exc.status_code >= 500:
            log_event("api_error", request_id=rid, code=exc.code, status=exc.status_code, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, rid, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []))
            fields.append({"field": loc or "body", "message": str(err.get("msg", "Invalid value"))})
        return JSONResponse(
            status_code=422,
            content=_payload(
                "VALIDATION_ERROR",
                "Request validation failed. Check the 'fields' list.",
                _request_id(),
                fields=fields,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, str(exc.detail), _request_id()),
        )

    @app.exception_handler(asyncpg.PostgresError)
    async def _postgres_error(request: Request, exc: asyncpg.PostgresError):
        state = getattr(exc, "sqlstate", None) or ""
        if state.startswith("08"):
            status, code, message = 503, "DATABASE_UNAVAILABLE", (
                "The database is temporarily unavailable (it may be waking up). "
                "It is safe to retry; with an Idempotency-Key no duplicate booking is created."
            )
        else:
            status, code, message = _SQLSTATE.get(
                state, (500, "DATABASE_ERROR", "Unexpected database error.")
            )
        rid = _request_id()
        log_event("db_error", request_id=rid, sqlstate=state, status=status, detail=str(exc))
        return JSONResponse(status_code=status, content=_payload(code, message, rid))

    @app.exception_handler(OSError)
    @app.exception_handler(TimeoutError)
    async def _network_error(request: Request, exc: Exception):
        rid = _request_id()
        log_event("network_error", request_id=rid, detail=str(exc))
        return JSONResponse(
            status_code=503,
            content=_payload(
                "DATABASE_UNAVAILABLE",
                "Could not reach the database. It is safe to retry; with an "
                "Idempotency-Key no duplicate booking is created.",
                rid,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = _request_id()
        log_event(
            "unhandled_error",
            request_id=rid,
            path=request.url.path,
            error=repr(exc),
            trace=traceback.format_exc(limit=8),
        )
        return JSONResponse(
            status_code=500,
            content=_payload(
                "INTERNAL",
                "Unexpected server error. It is safe to retry; with an "
                "Idempotency-Key no duplicate booking is created.",
                rid,
            ),
        )

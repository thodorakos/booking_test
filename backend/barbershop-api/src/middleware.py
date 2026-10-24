"""Pure-ASGI middleware: CORS, rate limits, security headers and body limits.

Kept dependency-free (no Starlette middleware base classes) so it behaves
identically on Cloudflare Workers (Python) and any other ASGI host.

CORS origins are read per request from ALLOWED_ORIGINS; use exact origins.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from config import DEFAULTS, env_from_scope, settings_for
from errors import ApiError, _payload, _request_id, log_event
from security import admin_key_valid

MAX_BODY_BYTES = 64 * 1024
ALLOWED_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
ALLOWED_HEADERS = "content-type, x-admin-key, idempotency-key"
MAX_AGE = "600"


def _headers(scope) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers") or []
    }


def allowed_origin(origin: str | None, env) -> str | None:
    try:
        raw = getattr(env, "ALLOWED_ORIGINS")
    except AttributeError:
        raw = None
    allowed = tuple(o.strip() for o in str(raw or DEFAULTS["ALLOWED_ORIGINS"]).split(","))
    if origin is None:
        return None
    if "*" in allowed:
        return "*"
    return origin if origin in allowed else None


def payload_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content=_payload("PAYLOAD_TOO_LARGE", "Request body exceeds 64 KiB.", _request_id()),
    )


def response_headers(origin: str | None, env, secure: bool) -> dict[str, str]:
    headers = {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "vary": "Origin",
    }
    if secure:
        headers["strict-transport-security"] = "max-age=31536000"
    grant = allowed_origin(origin, env)
    if grant:
        headers["access-control-allow-origin"] = grant
        headers["access-control-expose-headers"] = "Retry-After, Idempotent-Replay"
    return headers


class RateLimitMiddleware:
    """Use edge counters, never process-local state or caller-supplied identities."""

    # shortcut: edge counters are approximate per location; use durable storage for strict global quotas.

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        env = env_from_scope(scope)
        headers = _headers(scope)
        # Cloudflare overwrites this header; X-Forwarded-For is not trusted.
        ip = headers.get("cf-connecting-ip") or (scope.get("client") or ("unknown",))[0]
        path = scope["path"].rstrip("/")
        checks = [("API_RATE_LIMITER", "api")]
        if path == "/bookings" or path.startswith("/bookings/"):
            checks.append(("SENSITIVE_RATE_LIMITER", "bookings"))
        if path == "/admin" or path.startswith("/admin/") or "x-admin-key" in headers:
            request = Request(scope)
            try:
                authenticated = admin_key_valid(request, settings_for(request))
            except ApiError:
                authenticated = False
            if not authenticated:
                checks.append(("SENSITIVE_RATE_LIMITER", "admin-auth"))
        for binding, bucket in checks:
            try:
                limiter = getattr(env, binding)
                result = await limiter.limit({"key": f"barbershop:v1:{bucket}:{ip}"})
                permitted = result["success"]
            except Exception:
                log_event("rate_limit_unavailable", binding=binding)
                response = JSONResponse(status_code=503, content=_payload(
                    "RATE_LIMIT_UNAVAILABLE", "Request protection is temporarily unavailable. Please retry.", _request_id()))
                await response(scope, receive, send)
                return
            if not permitted:
                response = JSONResponse(status_code=429, headers={"Retry-After": "60"}, content=_payload(
                    "RATE_LIMITED", "Too many requests. Please wait 60 seconds before retrying.", _request_id()))
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """Limit actual bytes read, including requests without Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        length = headers.get("content-length")
        try:
            declared_size = int(length or "0")
        except ValueError:
            declared_size = 0
        if declared_size > MAX_BODY_BYTES:
            await payload_too_large_response()(scope, receive, send)
            return

        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > MAX_BODY_BYTES:
                raise HTTPException(413, "Request body exceeds 64 KiB.")
            return message

        await self.app(scope, limited_receive, send)


class CorsMiddleware:
    """Reject untrusted browser origins and non-JSON writes; secure all responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        origin = headers.get("origin")
        env = env_from_scope(scope)
        grant = allowed_origin(origin, env)
        extra = response_headers(origin, env, scope.get("scheme") == "https")

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                existing = [(key, value) for key, value in message.get("headers", [])
                            if key.lower().decode("latin-1") not in extra]
                message["headers"] = existing + [(key.encode("latin-1"), value.encode("latin-1"))
                                                 for key, value in extra.items()]
            await send(message)

        if origin is not None and grant is None:
            response = JSONResponse(status_code=403, content=_payload(
                "ORIGIN_NOT_ALLOWED", "This origin is not allowed.", _request_id()))
            await response(scope, receive, send_wrapped)
            return

        is_preflight = (
            origin is not None
            and scope["method"] == "OPTIONS"
            and "access-control-request-method" in headers
        )
        if is_preflight:
            requested = {value.strip().lower() for value in headers.get("access-control-request-headers", "").split(",") if value.strip()}
            allowed = {value.strip().lower() for value in ALLOWED_HEADERS.split(",")}
            if headers["access-control-request-method"] not in ALLOWED_METHODS.split(", ") or not requested <= allowed:
                response = JSONResponse(status_code=403, content=_payload(
                    "CORS_NOT_ALLOWED", "This method or header is not allowed.", _request_id()))
                await response(scope, receive, send_wrapped)
                return
            await send_wrapped(
                {"type": "http.response.start", "status": 204, "headers": [
                    (b"access-control-allow-methods", ALLOWED_METHODS.encode("latin-1")),
                    (b"access-control-allow-headers", ALLOWED_HEADERS.encode("latin-1")),
                    (b"access-control-max-age", MAX_AGE.encode("latin-1")),
                ]}
            )
            await send({"type": "http.response.body", "body": b""})
            return

        if scope["method"] in {"POST", "PUT", "PATCH"} and headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            response = JSONResponse(status_code=415, content=_payload(
                "UNSUPPORTED_MEDIA_TYPE", "Send request bodies as application/json.", _request_id()))
            await response(scope, receive, send_wrapped)
            return

        await self.app(scope, receive, send_wrapped)

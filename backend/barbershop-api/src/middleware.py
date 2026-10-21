"""Pure-ASGI middleware: configurable CORS and a request body size limit.

Kept dependency-free (no Starlette middleware base classes) so it behaves
identically on Cloudflare Workers (Python) and any other ASGI host.

CORS origins are read per request from the ALLOWED_ORIGINS env var, so you
can change them in wrangler.jsonc without touching code. "*" allows any
origin (fine for a cookie-less public API); or list exact origins
comma-separated.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from config import DEFAULTS, env_from_scope
from errors import _payload, _request_id

MAX_BODY_BYTES = 64 * 1024
ALLOWED_METHODS = "GET, POST, OPTIONS"
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
    """Minimal CORS: preflight short-circuit + allow-origin on responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        origin = headers.get("origin")
        grant = allowed_origin(origin, env_from_scope(scope))

        is_preflight = (
            origin is not None
            and scope["method"] == "OPTIONS"
            and "access-control-request-method" in headers
        )
        if is_preflight:
            response_headers = []
            if grant:
                requested = headers.get("access-control-request-headers", "Content-Type")
                response_headers = [
                    (b"access-control-allow-origin", grant.encode("latin-1")),
                    (b"access-control-allow-methods", ALLOWED_METHODS.encode("latin-1")),
                    (b"access-control-allow-headers", requested.encode("latin-1")),
                    (b"access-control-max-age", MAX_AGE.encode("latin-1")),
                ]
            await send(
                {"type": "http.response.start", "status": 204, "headers": response_headers}
            )
            await send({"type": "http.response.body", "body": b""})
            return

        if grant is None:
            await self.app(scope, receive, send)
            return

        extra = [(b"access-control-allow-origin", grant.encode("latin-1"))]
        if grant != "*":
            extra.append((b"vary", b"Origin"))

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers") or []) + extra
            await send(message)

        await self.app(scope, receive, send_wrapped)

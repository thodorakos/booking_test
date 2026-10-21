"""Postgres access via asyncpg.

On Cloudflare Workers the connection goes through the Hyperdrive binding
(env.HYPERDRIVE), which pools and accelerates the underlying Neon
connection. TLS to Neon is terminated inside Hyperdrive, so the local hop
uses ssl=False — exactly like the official example at
developers.cloudflare.com/hyperdrive/examples/python-workers/.

Outside Workers (local tooling, alternative ASGI hosting) a plain
DATABASE_URL DSN is used instead (sslmode comes from the DSN itself).

Each request opens one short-lived connection and closes it in a finally
block; Hyperdrive keeps the underlying pool warm, so this is cheap. Query
timeouts are passed per-statement by the route handlers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg

from config import env_from_scope
from errors import ApiError

CONNECT_TIMEOUT_SECONDS = 10.0


def _hyperdrive(env):
    try:
        return getattr(env, "HYPERDRIVE")
    except AttributeError:
        return None


async def _open(env) -> asyncpg.Connection:
    hd = _hyperdrive(env)
    if hd is not None:
        # Official Hyperdrive + Python Workers pattern.
        return await asyncpg.connect(
            host=hd.host,
            port=int(hd.port),
            user=hd.user,
            password=hd.password,
            database=hd.database,
            ssl=False,  # TLS to Neon is terminated by Hyperdrive itself
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
    dsn = None
    try:
        dsn = getattr(env, "DATABASE_URL")
    except AttributeError:
        dsn = None
    if dsn:
        return await asyncpg.connect(dsn=str(dsn), timeout=CONNECT_TIMEOUT_SECONDS)
    raise ApiError(
        503,
        "DATABASE_UNAVAILABLE",
        "No database configured: expected the HYPERDRIVE binding (Workers) or DATABASE_URL.",
    )


@asynccontextmanager
async def db_connection(request):
    """Yield one asyncpg connection for the duration of a request."""
    env = env_from_scope(request.scope)
    conn = await _open(env)
    try:
        yield conn
    finally:
        try:
            await conn.close()
        except Exception:
            pass

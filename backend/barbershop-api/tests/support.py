"""Disposable Postgres databases for API and Workers checks."""

import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@asynccontextmanager
async def isolated_database():
    dsn = os.environ["TEST_DATABASE_URL"]
    control = await asyncpg.connect(dsn)
    name = "booking_test_" + uuid.uuid4().hex
    conn = None
    created = False
    try:
        await control.execute(f"CREATE DATABASE {name}")
        created = True
        parts = urlsplit(dsn)
        test_dsn = urlunsplit(parts._replace(path="/" + name))
        conn = await asyncpg.connect(test_dsn)
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            await conn.execute(migration.read_text())
        yield conn, test_dsn
    finally:
        if conn is not None:
            await conn.close()
        if created:
            await control.execute(f"DROP DATABASE {name} WITH (FORCE)")
        await control.close()

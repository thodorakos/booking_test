https://developers.cloudflare.com/workers/best-practices/workers-best-practices/
https://developers.cloudflare.com/workers/local-development/
https://developers.cloudflare.com/workers/languages/python/packages/fastapi/
https://developers.cloudflare.com/workers/databases/connecting-to-databases/
https://developers.cloudflare.com/hyperdrive/
https://developers.cloudflare.com/workers/databases/third-party-integrations/neon/
https://neon.com/docs/introduction

READ ALL THE DOCS before anything. read all the docs for workers and fastapi and neon . we will make a cloudflare fastapi backend + neon db.   we will make a robust not over-enginnered booking system for a barber shop. 4 barbers. you book with one of them a fixed set of 5 servises at a specific day/hour. haircuts last 30 mins. haircuts + beard 45. more complex hair apoiment 1 hour. the booking system must be robust and make sure no bookings will get lost and we want fall on an edge case. the backend system must be profesional and robust.  no over-enginering. DO NOT create a frontend , it already exists

## 1. Runtime & framework

| Name | Role | Docs |
|---|---|---|
| **Cloudflare Workers (Python)** | Runtime | [developers.cloudflare.com/workers/languages/python](https://developers.cloudflare.com/workers/languages/python/) |
| **FastAPI** | API framework | [developers.cloudflare.com/workers/languages/python/packages/fastapi](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/) |
| **uv** | Package/env manager | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| **pywrangler** (from `workers-py`) | Dev & deploy CLI | [developers.cloudflare.com/workers/languages/python/#develop-and-deploy](https://developers.cloudflare.com/workers/languages/python/) — usage shown in the FastAPI page above |
| **Wrangler config** (`wrangler.jsonc`) | Binding + compat-date config | [developers.cloudflare.com/wrangler/configuration](https://developers.cloudflare.com/wrangler/configuration/) |

## 2. Data layer

| Name | Role | Docs |
|---|---|---|
| **Neon Postgres** | Database | [neon.com/docs/introduction](https://neon.com/docs/introduction) |
| **Hyperdrive** | Edge connection pooling | [developers.cloudflare.com/hyperdrive](https://developers.cloudflare.com/hyperdrive/) |
| **Hyperdrive + Python Workers** | Driver setup (`asyncpg`, compat date `2026-09-08`) | [developers.cloudflare.com/hyperdrive/examples/python-workers](https://developers.cloudflare.com/hyperdrive/examples/python-workers/) |
| **asyncpg** | Postgres driver (recommended, tested) | [magicstack.github.io/asyncpg](https://magicstack.github.io/asyncpg/) + the Hyperdrive Python page above |
| **Pydantic v2** | Payload validation | [docs.pydantic.dev](https://docs.pydantic.dev/) |
| **Hyperdrive ↔ Neon connection guide** | Use Neon's **direct** (non-`-pooler`) string | [developers.cloudflare.com/workers/databases/third-party-integrations/neon](https://developers.cloudflare.com/workers/databases/third-party-integrations/neon/) |

## 3. Correctness (Postgres features — no extra tools, just SQL)

| Name | Role | Docs |
|---|---|---|
| **`btree_gist` extension** | Enables the anti-overlap constraint | [neon.com/docs/extensions](https://neon.com/docs/extensions) + [postgresql.org/docs → btree_gist](https://www.postgresql.org/docs/current/btree-gist.html) |
| **`EXCLUDE USING gist`** + `tstzrange` | DB-guaranteed double-booking rejection | [postgresql.org/docs → CREATE TABLE ... EXCLUDE](https://www.postgresql.org/docs/current/sql-createtable.html#SQL-CREATETABLE-EXCLUDE) |
| **`SELECT ... FOR UPDATE`** | Serializes quota/capacity read-modify-write | [postgresql.org/docs → row locking](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) |
| **Unique constraint on idempotency key** | Safe payment-webhook retries | [postgresql.org/docs → CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html) |

## 4. Ops (the only two extras)

| Name | Role | Docs |
|---|---|---|
| **Workers Cron Triggers** | Sweep expired holds (not pg_cron — it sleeps with scale-to-zero) | [developers.cloudflare.com/workers/configuration/cron-triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/) |
| **Neon scale-to-zero setting** | Disable on the primary branch in production | [neon.com/docs/introduction/scale-to-zero](https://neon.com/docs/introduction/scale-to-zero) |

**Optionally** (only if the project grows): **Alembic** for versioned migrations ([alembic.sqlalchemy.org](https://alembic.sqlalchemy.org/)) — otherwise plain `.sql` files run from CI are enough — and **Neon branching** for per-PR test databases ([neon.com/docs/introduction/branching](https://neon.com/docs/introduction/branching)).

That's the whole inventory: 5 runtime pieces, 6 data pieces, 4 SQL features, 2 ops settings. The double-booking guarantee comes from one `CREATE EXTENSION` + one `EXCLUDE` constraint — no locks library, no Redis, no queue.
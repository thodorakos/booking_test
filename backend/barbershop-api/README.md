# Barbershop Booking API

Robust, deliberately simple booking backend for a small barbershop.
**Cloudflare Workers (Python) + FastAPI + Neon Postgres via Hyperdrive.**
The Astro frontend is in `../../frontend`. It reads the catalog and availability
at runtime and includes `/book`, `/manage` and `/admin` pages. Set its
`PUBLIC_API_URL` to this API's origin and allow the frontend origin in
`ALLOWED_ORIGINS`. Admin access uses the existing `ADMIN_API_KEY` entered in the
admin page; never put that secret in a public frontend environment variable.

```
existing frontend ──HTTPS──> Cloudflare Worker (FastAPI, Python)
                                   │
                                   │ asyncpg (ssl off, TLS ends here)
                                   ▼
                              Hyperdrive  ─── pooled, TLS ───▶  Neon Postgres
                                                                   │
                                        EXCLUDE USING gist constraint
                                        = no double bookings, ever
```

**Stack** (exactly five moving parts): `workers-py`/`pywrangler` CLI, FastAPI,
asyncpg, Hyperdrive, Neon. No ORM, no Redis, no queues, no auth framework —
correctness comes from plain Postgres features (`btree_gist` + `tstzrange`
exclusion constraint, unique idempotency key, FK checks).

---

## Shop policy encoded in this system

| Rule | Value | Where |
|---|---|---|
| Barbers | 4 starter rows; add/edit/deactivate through admin | `migrations/002_seed.sql`, `/admin/barbers` |
| Services | 5 starter services; names, duration, price and status editable through admin | `migrations/002_seed.sql`, `/admin/services` |
| Opening hours | Mon–Sat 09:00–19:00, closed Sundays | `wrangler.jsonc` vars |
| Slot grid | starts at :00 / :30 | `wrangler.jsonc` vars |
| Booking window | min 1h lead time, max 60 days ahead | `wrangler.jsonc` vars |
| Cancellation | free until **24h** before start (admin can always cancel) | `wrangler.jsonc` vars |
| Timezone | Europe/Athens (storage is always UTC) | `wrangler.jsonc` vars |
| Prices | EUR cents on services (editable) | `migrations/002_seed.sql` |

Hours, time zone, grid and booking windows are environment variables (see
[Configuration](#configuration)). Barbers and services are database rows.

---

## Why no booking can be lost or duplicated

| Concern | Guarantee | Mechanism |
|---|---|---|
| Two customers grab the same slot simultaneously | Exactly one wins; loser gets `409 SLOT_TAKEN`, or a retryable `503` if Postgres detects a deadlock | Postgres `EXCLUDE USING gist (barber_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE (status='confirmed')` rejects overlapping inserts |
| Client retries after a network timeout | No duplicate booking | `idempotency_key` UNIQUE + normalized request fingerprint; matching retries return the original booking (`200` + `Idempotent-Replay: true`), changed payloads get `409 IDEMPOTENCY_CONFLICT` |
| Booking "committed but response lost" | Same as above — retry returns it | Same |
| Neon asleep / connection blip | `503 DATABASE_UNAVAILABLE`, safe to retry | sqlstate `08***` mapped to a typed 503; idempotency makes retry harmless |
| Cancel then immediately rebook the slot | Works instantly | Partial exclusion constraint ignores `status='cancelled'` rows |
| Cancel racing a new booking on the same slot | No overlap; a conflicting create may need retrying after cancellation | The exclusion constraint and status-guarded update protect the slot |
| Double-cancel (two taps / retry) | Second gets `409 ALREADY_CANCELLED`, not a second write | `UPDATE ... WHERE status='confirmed'` guard |
| DST transitions (clocks jump) | Nonexistent/ambiguous local times rejected with a clear `422` | explicit fold/round-trip checks in `src/timeutils.py` (Athens transitions are 03:00–04:00 Sundays — shop closed — so they never fire in practice) |
| Service price/duration changes later | Existing bookings keep their agreed price and exact duration | Price is stored per booking; duration comes from its stored start/end times |
| Unknown/deactivated barber or service | `404` with distinct codes | FK + `is_active` checks before insert |
| Admin removes or edits a catalog entry during booking | The booking uses the locked catalog values or sees the completed change; existing appointments remain intact | Shared row locks held through insertion; removal only sets `is_active=false` |
| Booking spans closing time / past time / > horizon / off-grid | `422` with distinct codes | New-booking rules run after matching existing requests are recovered |
| Oversized/malformed requests | `413` / `422` with field-level details | Worker byte limit before ASGI, ASGI byte counter, Pydantic |
| Availability says free but slot taken between GET and POST | POST is the authority: `409 SLOT_TAKEN` | availability is advisory; the constraint decides |

The frontend contract for all of this: **read the `error.code`** and branch
(`SLOT_TAKEN` → re-fetch availability; `503`/`500` → safe to retry the same
request because you sent an `Idempotency-Key`).

---

## Setup (one-time, ~15 minutes)

### 0. Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.13+ is fetched automatically)
- Node.js 22+ and npm (`npm ci` installs the pinned local Wrangler)
- A Cloudflare account (Workers free tier is enough)
- A Neon account (free tier works to start)

### 1. Neon database

1. Create a project (region close to your customers, e.g. `eu-central-1`).
2. **Roles → New role** → `hyperdrive-user`, save the password.
3. Dashboard → Connection Details → pick the branch (`main`), database
   (`neondb`), role (`hyperdrive-user`) → select `psql` and **uncheck
   "Connection pooling"** → copy the **direct** connection string
   (`postgres://hyperdrive-user:...@ep-xxx...neon.tech/neondb`).
   > Use the direct (non `-pooler`) string — Hyperdrive does the pooling.
4. Run the migrations in order (Neon Console → SQL editor, or):
   ```bash
   psql "postgres://hyperdrive-user:PASSWORD@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require" \
     -v ON_ERROR_STOP=1 -f migrations/001_init.sql -f migrations/002_seed.sql \
     -f migrations/003_booking_snapshot.sql
   ```
5. **Production**: on a paid Neon plan, disable *Scale to Zero* on the
   primary branch compute (Console → Project → Settings → Compute) so the
   database never cold-starts during business hours.

### 2. Hyperdrive

```bash
uv run pywrangler hyperdrive create barbershop-db \
  --caching-disabled \
  --connection-string="postgres://hyperdrive-user:PASSWORD@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require"
```

Copy only the printed `id` into `wrangler.jsonc` → `hyperdrive[0].id`.
Keep credentials out of that file. For local development, export
`CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE` with a local or
dedicated test database URL. The `DATABASE_URL` fallback does not override a binding.

Query caching must stay **disabled**: cached misses break idempotent retries,
and writes do not invalidate Hyperdrive read caches. Pooling still works with
caching off. For an existing configuration, run:

```bash
uv run pywrangler hyperdrive update <HYPERDRIVE_ID> --caching-disabled
```

Confirm `caching.disabled` is true with `uv run pywrangler hyperdrive get <HYPERDRIVE_ID>`
before deploying. See [Hyperdrive query caching](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/).

### 3. Secrets

```bash
cp .dev.vars.example .dev.vars        # local: set ADMIN_API_KEY
uv run pywrangler secret put ADMIN_API_KEY   # production
```

Generate a strong key, e.g. `openssl rand -hex 32`.

### 4. Local dev

```bash
npm ci                                 # pinned Wrangler
uv sync --frozen                        # locked Python dependencies
export CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE="postgres://user:password@localhost:5432/barbershop"
uv run pywrangler dev                  # http://localhost:8787
curl http://localhost:8787/health
```

Interactive API docs: `http://localhost:8787/docs`.

Local credentials stay in the shell environment; do not paste them into tracked config.
See [Hyperdrive local development](https://developers.cloudflare.com/hyperdrive/configuration/local-development/).

### Checks before deploy

Use a disposable Postgres server with a role that can create databases. Each
test creates a separate randomly named database, applies all migrations and
removes that database afterwards. The configured database's tables are untouched.

```bash
export TEST_DATABASE_URL="postgres://postgres:password@localhost:5432/postgres"
uv run python -m unittest discover -s tests -v
uv run python tests/worker_smoke.py
uv run pywrangler deploy --dry-run
```

The suite covers overlap and idempotency races, request changes, policy changes,
price history, catalog management/auth/validation, concurrent deactivation,
cancellation/rebooking, private lookup, DST, body-size boundaries, rate-limit enforcement,
origin/JSON checks and security headers (including errors).
The smoke check starts the real local Python Worker and checks Postgres access,
admin catalog creation/edit/removal, booking/replay/conflict, CORS, native rate-limit bindings
and streamed bodies at/over 64 KiB. Its log is
`.wrangler/worker-smoke.log`. Unit/body checks run without `TEST_DATABASE_URL`;
database checks are skipped until it is set.

Keep both lockfiles in version control: `uv.lock` pins the development
environment; `pylock.toml` pins the WebAssembly packages bundled by pywrangler.
This compatibility date selects Python 3.14 in Workers.

### 5. Deploy

```bash
uv run pywrangler deploy
```

You get a `https://barbershop-api.<your-subdomain>.workers.dev` URL (or attach
a custom domain / route in the Cloudflare dashboard). Verify:

```bash
curl https://<your-worker-url>/health
curl https://<your-worker-url>/services
```

Then set the real `ALLOWED_ORIGINS` in `wrangler.jsonc` `vars` (e.g.
`https://book.yourshop.gr`) and redeploy. `*` works but exact origins are
tighter.

---

## API reference

`GET /shop` returns the public runtime policy: `timezone`, `currency` (EUR),
`open_time`, `close_time`, `closed_weekdays` (0=Mon, 6=Sun),
`booking_horizon_days`, `booking_lead_minutes`, and `cancel_cutoff_hours`.
The frontend uses this endpoint to keep displayed hours and booking rules in sync.

Base URL: `https://<your-worker>.workers.dev` — JSON everywhere.
All timestamps come in **two forms**: absolute `starts_at` / `ends_at
("2026-10-25T11:00:00Z")` and shop-local `starts_at_local` /
`ends_at_local` (`"2026-10-25T14:00"`). Requests take **shop-local wall time**.

Seeded ids for testing (from `002_seed.sql`):

- Barbers: `11000000-0000-4000-8000-00000000000{1..4}`
- Services: `22000000-0000-4000-8000-00000000000{1..5}`

### `GET /health`
`200 {"status":"ok","database":"ok","version":"1.0.0"}` or `503` when the DB is unreachable.

### `GET /barbers` — list active barbers
```json
[{"id":"11000000-0000-4000-8000-000000000001","name":"Nikos Papadakis"}]
```

### `GET /services` — active services
```json
[{"id":"22000000-0000-4000-8000-000000000001","name":"Haircut",
   "duration_minutes":30,"price_cents":1500}]
```

### `GET /availability?barber_id=…&service_id=…&date=2026-10-26`
Bookable start times for that barber + service (duration-aware) on a day.
```json
{"barber_id":"…","barber_name":"Nikos Papadakis","service_id":"…",
 "service_name":"Haircut + beard","date":"2026-10-26","duration_minutes":45,
 "closed":false,
 "available":[{"starts_at":"2026-10-26T08:00:00Z","starts_at_local":"2026-10-26T11:00"}]}
```
Closed day → `"closed": true, "available": []`. Past/beyond-horizon days → empty list.

### `POST /bookings` — create a booking
```json
{
  "barber_id":    "11000000-0000-4000-8000-000000000001",
  "service_id":   "22000000-0000-4000-8000-000000000003",
  "starts_at":    "2026-10-26T11:00",
  "customer_name": "Giannis P.",
  "customer_phone": "+30 691 234 5678",
  "notes": "fade #2 on the sides",
  "idempotency_key": "web-8f3a2c1d"
}
```
- `starts_at` is **shop-local wall time**; `ends_at` is computed by the server
  from the service duration — never send it.
- `idempotency_key` (or `Idempotency-Key` header): **send one on every create
  from the frontend** (any client-generated unique string, 8–100 chars). It is
  what makes retries after timeouts safe.
- `201` → the booking (see below). Same key and normalized payload retried →
  `200` with the original booking + `Idempotent-Replay: true` header, even if
  hours, horizon, time zone or catalog availability have since changed.
- Reusing the key with a different payload → `409 IDEMPOTENCY_CONFLICT`, with
  no original customer details. Use a new key for a new appointment.
- Someone booked the same slot first → `409 SLOT_TAKEN` → re-fetch
  availability.

Response body (also returned by GET/cancel):
```json
{
  "id":"9b41…","status":"confirmed",
  "barber_id":"…","barber_name":"Nikos Papadakis",
  "service_id":"…","service_name":"Haircut + beard",
  "duration_minutes":45,"price_cents":2000,
  "starts_at":"2026-10-26T08:00:00Z","ends_at":"2026-10-26T08:45:00Z",
  "starts_at_local":"2026-10-26T11:00","ends_at_local":"2026-10-26T11:45",
  "customer_name":"Giannis P.","customer_phone":"+306912345678",
  "notes":"fade #2 on the sides","idempotency_key":"web-8f3a2c1d",
  "cancellation_reason":null,"cancelled_at":null,"created_at":"…"
}
```

### `POST /bookings/{id}/lookup`
Owner lookup with `{"phone":"+306912345678"}` in the JSON body. The phone must
match the booking; the frontend keeps it out of request URLs and access logs.
The original `GET /bookings/{id}?phone=…` remains compatible for existing clients;
prefer POST for new clients. A valid `X-Admin-Key` also permits lookup.

### `POST /bookings/{id}/cancel` — customer cancellation
```json
{"phone": "+306912345678"}
```
Frees the slot instantly. After the 24h cutoff → `422 TOO_LATE_TO_CANCEL`
(the shop can still cancel via admin).

### `GET /schedule?barber_id=…&date=2026-10-26` — public day calendar
Times + service names + status, **no customer PII** — safe to render publicly.

### Admin (header `X-Admin-Key: <secret>`)

| Endpoint | Purpose |
|---|---|
| `GET /admin/barbers` | List all barbers, including inactive ones |
| `POST /admin/barbers` | Add a barber |
| `PUT /admin/barbers/{id}` | Replace name and active status; also restores an inactive barber |
| `DELETE /admin/barbers/{id}` | Deactivate a barber |
| `GET /admin/services` | List all services, including inactive ones |
| `POST /admin/services` | Add a service |
| `PUT /admin/services/{id}` | Replace name, duration, price and active status; also restores a service |
| `DELETE /admin/services/{id}` | Deactivate a service |
| `GET /admin/bookings?from=2026-10-26&to=2026-10-26[&barber_id=…][&include_cancelled=false]` | Full calendar incl. names/phones; inclusive date range with no day-count limit; defaults to today in the shop timezone |
| `POST /admin/bookings/{id}/cancel` body `{"reason":"no-show"}` | Cancel any booking any time |

Create/update payloads:

```json
{"name":"Barber #5","is_active":true}
```

```json
{"name":"Haircut","duration_minutes":30,"price_cents":1500,"is_active":true}
```

Names are trimmed and must contain 1–80 characters. Durations must be integers
from 5 to 240 minutes; prices are optional integer cents from 0 to 2147483647
(`null` means unspecified). Unknown fields are rejected. `is_active` defaults
to `true`. **PUT replaces all editable fields**: send the full item, including
its intended status and price. Omitted prices become `null`.

POST returns `201`; PUT and DELETE return `200`. Admin items include `id` and
`is_active` alongside their fields. Unknown IDs return `404 BARBER_NOT_FOUND`
or `404 SERVICE_NOT_FOUND`; malformed UUIDs return `422`.

DELETE archives the row and is safe to repeat. Public catalog/availability and
new bookings exclude inactive entries. Existing appointments remain confirmed,
readable and cancellable, and matching retries still replay. Review future
appointments in `/admin/bookings` and contact customers/cancel explicitly when
a barber leaves; removing a barber does not cancel their calendar. A booking
that wins the catalog lock can finish before deactivation completes.

### Error envelope (all errors, all endpoints)

```json
{"error": {"code": "SLOT_TAKEN", "message": "…", "request_id": "a1b2c3d4e5f6"}}
```

| `code` | HTTP | Meaning / frontend action |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Bad payload — see `error.fields[]` |
| `INVALID_START_TIME` / `INVALID_DATE` / `INVALID_DATE_RANGE` | 422 | Malformed or impossible date/time |
| `CLOSED_DAY` | 422 | Shop closed that weekday |
| `OUTSIDE_OPENING_HOURS` | 422 | Doesn't fit inside opening hours |
| `SLOT_NOT_ALIGNED` | 422 | Not on the :00/:30 grid |
| `TOO_LATE_TO_BOOK` | 422 | Less than 1h lead time (or in the past) |
| `TOO_FAR_AHEAD` | 422 | Beyond the 60-day horizon |
| `TOO_LATE_TO_CANCEL` | 422 | Past the 24h cutoff — call the shop |
| `BARBER_NOT_FOUND` / `SERVICE_NOT_FOUND` / `BOOKING_NOT_FOUND` | 404 | Refresh catalog |
| `SLOT_TAKEN` | 409 | Someone booked first — re-fetch availability |
| `IDEMPOTENCY_CONFLICT` | 409 | Key belongs to a different request or predates request fingerprinting |
| `ALREADY_CANCELLED` | 409 | Already cancelled (retry-safe signal) |
| `PHONE_REQUIRED` / `PHONE_MISMATCH` | 401 | Customer verification failed |
| `FORBIDDEN` | 401 | Bad admin key |
| `ADMIN_DISABLED` | 503 | `ADMIN_API_KEY` secret not set |
| `DATABASE_UNAVAILABLE` / `QUERY_TIMEOUT` / `RETRY_LATER` | 503 | **Safe to retry** (with the same idempotency key) |
| `PAYLOAD_TOO_LARGE` | 413 | Body over 64 KiB |
| `RATE_LIMITED` | 429 | Wait for `Retry-After` seconds before retrying; CORS exposes this header |
| `RATE_LIMIT_UNAVAILABLE` | 503 | Rate-limit binding missing or unavailable; requests fail closed |
| `ORIGIN_NOT_ALLOWED` / `CORS_NOT_ALLOWED` | 403 | Browser origin, preflight method or header is not allowed |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Send POST/PUT bodies as `application/json` |
| `CONFIG_ERROR` / `INTERNAL` | 500 | Server-side; check logs via request_id |

---

## Configuration

All runtime knobs are `vars` in `wrangler.jsonc` (safe defaults in code):

| Var | Default | Notes |
|---|---|---|
| `SHOP_TIMEZONE` | `Europe/Athens` | any IANA zone; storage is UTC |
| `SHOP_OPEN` / `SHOP_CLOSE` | `09:00` / `19:00` | local wall time |
| `SLOT_GRID_MINUTES` | `30` | must divide 60 |
| `BOOKING_LEAD_MINUTES` | `60` | minimum notice |
| `BOOKING_HORIZON_DAYS` | `60` | how far ahead |
| `CANCEL_CUTOFF_HOURS` | `24` | customer cutoff; admin ignores |
| `CLOSED_WEEKDAYS` | `6` | 0=Mon…6=Sun, comma-separated |
| `ALLOWED_ORIGINS` | `http://localhost:4321,http://127.0.0.1:4321` | comma-separated exact origins; production is set in Wrangler |
| `QUERY_TIMEOUT_SECONDS` | `8` | per-query asyncpg timeout |

Secrets: `ADMIN_API_KEY` (required for `/admin/*`).

## Security and request limits

The Worker uses [Cloudflare's native rate-limit bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/),
configured in `wrangler.jsonc`: 120 requests/minute per client IP across the API,
with separate 10/minute buckets for all customer booking operations combined
(create/lookup/cancel) and failed/missing admin credentials. Valid staff requests
use the general limit. Changing booking IDs, phone numbers, keys or
`X-Forwarded-For` does not reset these counters. OPTIONS preflights are exempt.
The trusted IP comes from Cloudflare's `CF-Connecting-IP` header.

These are approximate counters per Cloudflare location, suited to abuse prevention,
not strict global quotas. Both bindings are required, including in named Wrangler
environments; missing/broken bindings return 503 instead of allowing unprotected
requests. Standalone ASGI hosting must provide equivalent trusted bindings/edge
protection; regression tests supply fake counters. Reserve the two namespace IDs
for this application within your Cloudflare account.

Requests from disallowed browser origins are rejected before handlers execute.
POST/PUT require JSON, so ordinary HTML form posts cannot create or cancel bookings.
CORS is not authentication: direct clients still require booking ownership/admin
credentials where applicable. Responses disable caching and MIME sniffing, block
framing and referrers, and set HSTS over HTTPS. Keep HTTPS at the public edge,
use a strong random admin secret, and keep real secrets in Wrangler secrets.

## Before a public launch (no payments)

The booking/create/lookup/cancel flow and admin calendar are implemented.
The following gaps still need a launch decision:

| Priority | Work | Current behavior |
|---|---|---|
| Before accepting real appointments | Date-specific shop closures and barber time off, including lunch breaks and leave | Every active barber follows the same weekly shop hours; no date/time blockouts exist. Separate weekly schedules are only needed if staff hours differ. |
| If booking spam persists | Bot protection or phone verification on new bookings | IP rate limits are implemented. Phones remain unverified; consider [Turnstile with server-side validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/) or SMS verification if abuse warrants it. |
| Before connecting a staff dashboard | A private way for the owner/staff to authenticate | The backend accepts a shared admin key. Enter it privately or keep it behind a staff sign-in/server; never bundle it into public JavaScript. Individual staff access can use [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) when needed. |
| Before launch | Verify customer confirmation and return/cancel flow | The API returns a booking ID and supports lookup/cancellation. The customer must retain that reference. The frontend is outside this backend review. SMS/email reminders and rescheduling are useful follow-ups, not required for the first version. |
| Before launch | Complete live configuration and an operations check | Set the real Hyperdrive ID with caching disabled, apply migrations, set the admin secret, configure real catalog/hours/origins, test booking then cancellation on staging, arrange uptime/error alerts and rehearse [Neon restore](https://neon.com/docs/postgres/backup-restore/branch-restore). Local checks do not verify these account settings. |

All appointments are confirmed immediately. No payment integration, unpaid
holds or hold-expiry Cron Trigger is needed for this version.

## Day-to-day ops

- **Logs and traces**: both are enabled in `wrangler.jsonc`.
  `uv run pywrangler tail` (or dashboard → Workers Logs) shows structured
  events: `booking_created`, `booking_cancelled`, `db_error`,
  `unhandled_error` (+ `request_id` for cross-referencing error responses).
- **Manage barbers/services**: use the protected `/admin/barbers` and
  `/admin/services` endpoints above. DELETE deactivates; PUT with
  `is_active=true` restores the same ID. No new migration is needed for these routes.
- **Change a price/name/duration**: use `PUT /admin/services/{id}` — existing
  bookings keep their stored price and times; future bookings use the new values.
  Names continue to follow the current catalog.
- **Upgrading the original schema**: apply `003_booking_snapshot.sql` once,
  before deploying this code. Existing rows remain readable and cancellable.
  Their original prices were never stored, so the migration uses the current
  menu price. Existing idempotency keys without a fingerprint return a conflict;
  retrieve those bookings by ID and phone. New bookings get full snapshot/replay guarantees.
- **Schema changes**: add `migrations/00X_*.sql` and run it in the Neon SQL
  editor. Keep them forward-only and idempotent-ish; at this scale that's all
  you need (add Alembic only if migrations start feeling risky).
- **Backups / PITR**: Neon keeps point-in-time restore history on paid plans —
  the operational safety net for "a booking was deleted by mistake".
- **Neon branches**: spin a branch + a staging Hyperdrive + a
  `[env.staging]` block in `wrangler.jsonc` if you later want a test deploy.

## Project layout

```
wrangler.jsonc           Worker + Hyperdrive + policy vars
pyproject.toml           deps: fastapi, asyncpg, pydantic, tzdata (dev: workers-py)
package.json             pinned Wrangler development dependency
pylock.toml              locked Pyodide/WebAssembly runtime dependencies
migrations/001_init.sql  schema + EXCLUDE no-overlap constraint
migrations/002_seed.sql  4 barbers + 5 services (fixed UUIDs)
migrations/003_booking_snapshot.sql  stored price + request fingerprint
src/main.py              Worker byte limit + official ASGI entry
src/app.py               FastAPI app shared by Worker and regression checks
src/bookings.py          create/get/cancel/availability/schedule routes + SQL
src/admin.py             X-Admin-Key catalog management, calendar and shop-side cancel
src/catalog.py           /health /barbers /services
src/availability.py      slot engine (grid, hours, overlap, lead time)
src/timeutils.py         Athens wall-time <-> UTC, DST edge detection
src/api_models.py        Pydantic wire contract
src/db.py                asyncpg via Hyperdrive / DATABASE_URL
src/config.py            per-request settings from env
src/errors.py            one error envelope + SQLSTATE mapping
src/security.py          admin key + phone matching (constant-time)
src/middleware.py        CORS, native rate limits, security headers + body-size limit (pure ASGI)
tests/                  API/Postgres regression suite + real Workers smoke check
```

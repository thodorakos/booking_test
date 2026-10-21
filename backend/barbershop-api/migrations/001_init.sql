-- 001_init.sql — Barbershop booking schema (run once on an empty Neon database)
--
-- Correctness model (plain Postgres, no extra infrastructure):
--   * No double-booking, ever:  EXCLUDE USING gist ... WHERE (status = 'confirmed')
--     makes the database itself reject any INSERT that overlaps an existing
--     confirmed booking for the same barber — even under full concurrency.
--     Requires the btree_gist extension (available on Neon).
--   * Cancel-and-rebook:        cancelled rows are excluded from the constraint
--     (partial exclusion constraint), so a freed slot is instantly reusable.
--   * Safe client retries:      idempotency_key is UNIQUE; a retried request
--     returns the original booking instead of creating a duplicate.
--
-- Run in the Neon Console SQL editor, or:
--   psql "postgres://hyperdrive-user:PASSWORD@ep-xxxx...neon.tech/neondb?sslmode=require" -f migrations/001_init.sql

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Barbers (seeded in 002_seed.sql; deactivate with is_active = FALSE, never delete)
CREATE TABLE IF NOT EXISTS barbers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Services offered (the fixed menu; deactivate rather than delete)
CREATE TABLE IF NOT EXISTS services (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 5 AND 240),
    price_cents      INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bookings: one row per appointment. All times are TIMESTAMPTZ (absolute
-- instants, DST-proof). ends_at is computed by the API from the service
-- duration — clients never send it — so it can never disagree with the menu.
CREATE TABLE IF NOT EXISTS bookings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    barber_id           UUID NOT NULL REFERENCES barbers (id),
    service_id          UUID NOT NULL REFERENCES services (id),
    starts_at           TIMESTAMPTZ NOT NULL,
    ends_at             TIMESTAMPTZ NOT NULL,
    customer_name       TEXT NOT NULL CHECK (char_length(customer_name) BETWEEN 1 AND 80),
    customer_phone      TEXT NOT NULL CHECK (customer_phone ~ '^\+?[0-9]{6,15}$'),
    notes               TEXT CHECK (notes IS NULL OR char_length(notes) <= 500),
    status              TEXT NOT NULL DEFAULT 'confirmed'
                          CHECK (status IN ('confirmed', 'cancelled')),
    idempotency_key     TEXT UNIQUE,          -- safe retries / future payment webhooks
    cancellation_reason TEXT CHECK (cancellation_reason IS NULL OR char_length(cancellation_reason) <= 200),
    cancelled_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at),

    -- THE anti-double-booking guarantee:
    -- no two CONFIRMED bookings of the same barber may overlap in time.
    -- A partial exclusion constraint: cancelled rows leave the index, so
    -- their slots become immediately bookable again.
    EXCLUDE USING gist (
        barber_id WITH =,
        tstzrange(starts_at, ends_at) WITH &&
    ) WHERE (status = 'confirmed')
);

-- Serves day-range scans (admin calendar, schedule endpoint).
CREATE INDEX IF NOT EXISTS bookings_starts_at_idx ON bookings (starts_at);

-- (The UNIQUE on idempotency_key and the GiST exclusion index above already
-- cover their lookup paths; no further indexes are needed at this scale.)

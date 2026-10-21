-- Run after 001/002, before deploying the updated API. No bookings are deleted.
BEGIN;

ALTER TABLE bookings
    ADD COLUMN price_cents INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    ADD COLUMN request_fingerprint TEXT
        CHECK (request_fingerprint ~ '^[a-f0-9]{64}$');

-- Original prices were not recorded; only the current menu price is recoverable.
UPDATE bookings bk SET price_cents = s.price_cents
FROM services s WHERE s.id = bk.service_id;

-- Legacy keys have no fingerprint and cannot replay customer details.
-- Every new booking supplies a fingerprint; legacy rows remain readable/cancellable.
COMMIT;

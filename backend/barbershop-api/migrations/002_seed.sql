-- 002_seed.sql — starter data: 4 barbers and the 5 fixed services.
--
-- Fixed UUIDs so the frontend can rely on them in test environments.
-- Re-runnable: ON CONFLICT (id) DO NOTHING.
--
-- Adjust names/prices freely BEFORE go-live (after that, prefer updating
-- rows over changing ids). Price is in EUR cents; NULL means "no price".

INSERT INTO barbers (id, name) VALUES
    ('11000000-0000-4000-8000-000000000001', 'Nikos Papadakis'),
    ('11000000-0000-4000-8000-000000000002', 'Yiannis Georgiou'),
    ('11000000-0000-4000-8000-000000000003', 'Christos Dimitriou'),
    ('11000000-0000-4000-8000-000000000004', 'Dimitris Antoniou')
ON CONFLICT (id) DO NOTHING;

INSERT INTO services (id, name, duration_minutes, price_cents) VALUES
    ('22000000-0000-4000-8000-000000000001', 'Haircut',          30, 1500),
    ('22000000-0000-4000-8000-000000000002', 'Beard trim',       30,  800),
    ('22000000-0000-4000-8000-000000000003', 'Haircut + beard',  45, 2000),
    ('22000000-0000-4000-8000-000000000004', 'Kids cut',         30, 1000),
    ('22000000-0000-4000-8000-000000000005', 'Full restyle',     60, 3000)
ON CONFLICT (id) DO NOTHING;

import asyncio
import os
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import httpx

from support import ROOT, isolated_database
from app import app
from availability import compute_slots
from config import settings_from_env
from middleware import MAX_BODY_BYTES
from timeutils import WallClockError, naive_to_utc

BARBER = "11000000-0000-4000-8000-000000000001"
SERVICE = "22000000-0000-4000-8000-000000000001"


def client_for(env):
    async def application(scope, receive, send):
        scope["env"] = env
        await app(scope, receive, send)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="https://test.invalid"
    )


class TimeRules(unittest.TestCase):
    def test_dst_and_grid_alignment(self):
        st = settings_from_env(SimpleNamespace())
        for wall in (datetime(2026, 10, 25, 3, 30), datetime(2027, 3, 28, 3, 30)):
            with self.assertRaises(WallClockError):
                naive_to_utc(wall, st.tz)
        day = datetime(2026, 10, 26).date()
        for opened, grid, expected in ((time(9, 15), 30, "09:30"), (time(9, 15), 60, "10:00")):
            slots = compute_slots(day, 30, [], datetime(2026, 10, 20, tzinfo=timezone.utc),
                                  replace(st, open_time=opened, grid_minutes=grid))
            self.assertEqual(slots[0].astimezone(st.tz).strftime("%H:%M"), expected)
            self.assertTrue(all(slot.astimezone(st.tz).minute % grid == 0 for slot in slots))


class BodyLimit(unittest.IsolatedAsyncioTestCase):
    async def test_declared_streamed_and_underreported_sizes(self):
        async with client_for(SimpleNamespace(ALLOWED_ORIGINS="https://allowed.invalid")) as client:
            for size, expected in ((MAX_BODY_BYTES, 422), (MAX_BODY_BYTES + 1, 413)):
                body = b'{"padding":"' + b"x" * (size - 14) + b'"}'
                self.assertEqual(len(body), size)
                for declared in (None, "1", str(size)):
                    async def chunks():
                        for offset in range(0, len(body), 1024):
                            yield body[offset:offset + 1024]
                    headers = {"content-type": "application/json", "origin": "https://allowed.invalid"}
                    if declared is not None:
                        headers["content-length"] = declared
                    response = await client.post("/bookings", content=chunks(), headers=headers)
                    self.assertEqual(response.status_code, expected, response.text)
                    self.assertEqual(response.headers["access-control-allow-origin"], headers["origin"])
                    self.assertIn("request_id", response.json()["error"])
                    if expected == 413:
                        self.assertEqual(response.json()["error"]["code"], "PAYLOAD_TOO_LARGE")


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL to a disposable Postgres server")
class Bookings(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db, dsn = await self.enterAsyncContext(isolated_database())
        self.env = SimpleNamespace(DATABASE_URL=dsn, ADMIN_API_KEY="test-admin-key")
        self.client = await self.enterAsyncContext(client_for(self.env))
        self.day = datetime.now(settings_from_env(self.env).tz).date() + timedelta(days=7)
        while self.day.weekday() == 6:
            self.day += timedelta(days=1)
        self.payload = dict(barber_id=BARBER, service_id=SERVICE,
                            starts_at=f"{self.day}T10:00", customer_name="Test Customer",
                            customer_phone="+306900000001", notes="Test notes",
                            idempotency_key="test-booking-key")

    async def create(self, **changes):
        return await self.client.post("/bookings", json={**self.payload, **changes})

    async def test_matching_retry_and_changed_payload(self):
        created = await self.create()
        self.assertEqual(created.status_code, 201, created.text)
        retry = await self.create(customer_phone="+30 690 000 0001")
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json(), created.json())
        self.assertEqual(retry.headers["idempotent-replay"], "true")
        for changes in ({"customer_phone": "+306900000099"}, {"notes": "Different"},
                        {"starts_at": f"{self.day}T11:00"}):
            rejected = await self.create(**changes)
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(rejected.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")
            self.assertNotIn("customer_phone", rejected.text)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM bookings"), 1)

    async def test_retry_survives_policy_and_catalog_changes(self):
        created = await self.create()
        self.assertEqual(created.status_code, 201, created.text)
        self.env.BOOKING_HORIZON_DAYS = "1"
        self.env.CLOSED_WEEKDAYS = str(self.day.weekday())
        self.env.SHOP_TIMEZONE = "UTC"
        await self.db.execute("UPDATE services SET is_active = FALSE WHERE id = $1", uuid.UUID(SERVICE))
        retry = await self.create()
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["id"], created.json()["id"])

    async def test_same_key_races(self):
        first, second = await asyncio.gather(self.create(), self.create())
        self.assertEqual(sorted((first.status_code, second.status_code)), [200, 201])
        self.assertEqual(first.json()["id"], second.json()["id"])
        responses = await asyncio.gather(
            self.create(idempotency_key="test-different-race", starts_at=f"{self.day}T12:00"),
            self.create(idempotency_key="test-different-race", starts_at=f"{self.day}T13:00",
                        customer_phone="+306900000099"),
        )
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        loser = next(r for r in responses if r.status_code == 409)
        self.assertEqual(loser.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")

    async def test_overlap_adjacency_and_cancel_rebook(self):
        responses = await asyncio.gather(self.create(), self.create(idempotency_key="test-other-key"))
        self.assertEqual(sum(r.status_code == 201 for r in responses), 1)
        loser_index = next(i for i, r in enumerate(responses) if r.status_code != 201)
        loser = responses[loser_index]
        if loser.status_code == 503:
            loser = await self.create(idempotency_key=("test-booking-key", "test-other-key")[loser_index])
        self.assertEqual(loser.status_code, 409, loser.text)
        self.assertEqual(loser.json()["error"]["code"], "SLOT_TAKEN")
        adjacent = await self.create(starts_at=f"{self.day}T10:30", idempotency_key="test-adjacent")
        self.assertEqual(adjacent.status_code, 201, adjacent.text)
        booking = next(r.json() for r in responses if r.status_code == 201)
        cancelled = await self.client.post(f"/bookings/{booking['id']}/cancel", json={"phone": self.payload["customer_phone"]})
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        rebooked = await self.create(idempotency_key="test-after-cancel")
        self.assertEqual(rebooked.status_code, 201, rebooked.text)

    async def test_history_survives_menu_edits_in_every_response(self):
        created = await self.create()
        self.assertEqual(created.status_code, 201, created.text)
        await self.db.execute("UPDATE services SET duration_minutes=60, price_cents=9999 WHERE id=$1", uuid.UUID(SERVICE))
        lookup = await self.client.get(f"/bookings/{created.json()['id']}", params={"phone": self.payload["customer_phone"]})
        retry = await self.create()
        calendar = await self.client.get("/admin/bookings", params={"from": str(self.day)}, headers={"x-admin-key": self.env.ADMIN_API_KEY})
        cancelled = await self.client.post(f"/admin/bookings/{created.json()['id']}/cancel", json={}, headers={"x-admin-key": self.env.ADMIN_API_KEY})
        for booking in (lookup.json(), retry.json(), calendar.json()["bookings"][0], cancelled.json()):
            self.assertEqual(booking["duration_minutes"], 30)
            self.assertEqual(booking["price_cents"], 1500)
            self.assertEqual(booking["ends_at"], created.json()["ends_at"])

    async def test_offered_slots_can_be_booked(self):
        self.env.SHOP_OPEN = "09:15"
        availability = await self.client.get("/availability", params={"barber_id": BARBER, "service_id": SERVICE, "date": str(self.day)})
        self.assertEqual(availability.status_code, 200, availability.text)
        slot = availability.json()["available"][0]["starts_at_local"]
        self.assertTrue(slot.endswith("09:30"))
        booked = await self.create(starts_at=slot)
        self.assertEqual(booked.status_code, 201, booked.text)

    async def test_missing_catalog_ids_are_distinct(self):
        for field, code in (("service_id", "SERVICE_NOT_FOUND"), ("barber_id", "BARBER_NOT_FOUND")):
            response = await self.create(**{field: str(uuid.uuid4())})
            self.assertEqual(response.status_code, 404, response.text)
            self.assertEqual(response.json()["error"]["code"], code)

    async def test_legacy_key_fails_closed(self):
        await self.db.execute("ALTER TABLE bookings DROP COLUMN price_cents, DROP COLUMN request_fingerprint")
        start = naive_to_utc(datetime.fromisoformat(self.payload["starts_at"]), settings_from_env(self.env).tz)
        booking_id = await self.db.fetchval(
            """INSERT INTO bookings (barber_id, service_id, starts_at, ends_at,
                   customer_name, customer_phone, idempotency_key)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            uuid.UUID(BARBER), uuid.UUID(SERVICE), start, start + timedelta(minutes=30),
            self.payload["customer_name"], self.payload["customer_phone"], self.payload["idempotency_key"],
        )
        await self.db.execute((ROOT / "migrations/003_booking_snapshot.sql").read_text())
        retry = await self.create()
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(retry.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")
        lookup = await self.client.get(f"/bookings/{booking_id}", params={"phone": self.payload["customer_phone"]})
        self.assertEqual(lookup.status_code, 200, lookup.text)
        self.assertEqual(lookup.json()["price_cents"], 1500)
        self.assertEqual(lookup.json()["duration_minutes"], 30)


if __name__ == "__main__":
    unittest.main()

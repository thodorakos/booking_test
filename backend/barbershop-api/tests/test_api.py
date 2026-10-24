import asyncio
import os
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from support import ROOT, isolated_database
from app import app
from availability import compute_slots
from config import settings_from_env
from middleware import MAX_BODY_BYTES
from timeutils import WallClockError, naive_to_utc

BARBER = "11000000-0000-4000-8000-000000000001"
SERVICE = "22000000-0000-4000-8000-000000000001"


def client_for(env, *, raise_app_exceptions=True):
    for binding in ("API_RATE_LIMITER", "SENSITIVE_RATE_LIMITER"):
        if not hasattr(env, binding):
            setattr(env, binding, SimpleNamespace(limit=AsyncMock(return_value={"success": True})))
    async def application(scope, receive, send):
        scope["env"] = env
        await app(scope, receive, send)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, raise_app_exceptions=raise_app_exceptions), base_url="https://test.invalid"
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


class Middleware(unittest.IsolatedAsyncioTestCase):
    async def test_public_shop_policy_uses_runtime_settings(self):
        env = SimpleNamespace(SHOP_TIMEZONE="Europe/London", SHOP_OPEN="10:30",
                              CLOSED_WEEKDAYS="5,6", CANCEL_CUTOFF_HOURS="12",
                              BOOKING_HORIZON_DAYS="30", ADMIN_API_KEY="never-public")
        async with client_for(env) as client:
            response = await client.get("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "timezone": "Europe/London", "currency": "EUR", "open_time": "10:30",
            "close_time": "19:00", "closed_weekdays": [5, 6],
            "booking_horizon_days": 30, "booking_lead_minutes": 60,
            "cancel_cutoff_hours": 12,
        })

    async def test_admin_cors_preflight(self):
        env = SimpleNamespace(ALLOWED_ORIGINS="https://allowed.invalid")
        async with client_for(env) as client:
            for method in ("PUT", "DELETE"):
                response = await client.options(f"/admin/barbers/{BARBER}", headers={
                    "origin": "https://allowed.invalid",
                    "access-control-request-method": method,
                    "access-control-request-headers": "content-type,x-admin-key",
                })
                self.assertEqual(response.status_code, 204, response.text)
                self.assertEqual(response.headers["access-control-allow-origin"], env.ALLOWED_ORIGINS)
                self.assertIn(method, response.headers["access-control-allow-methods"].split(", "))
                self.assertIn("x-admin-key", response.headers["access-control-allow-headers"])

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

    async def test_private_lookup_and_cancel_require_the_owner_phone(self):
        created = await self.create()
        self.assertEqual(created.status_code, 201, created.text)
        path = f"/bookings/{created.json()['id']}"
        lookup = await self.client.post(path + "/lookup", json={"phone": "+30 690 000 0001"})
        self.assertEqual(lookup.status_code, 200, lookup.text)
        self.assertEqual(lookup.json(), created.json())
        self.assertEqual(lookup.headers["cache-control"], "no-store")
        for action in ("lookup", "cancel"):
            response = await self.client.post(f"{path}/{action}", json={"phone": "+306900000099"})
            self.assertEqual(response.status_code, 401, response.text)
            self.assertNotIn(self.payload["customer_phone"], response.text)
        legacy = await self.client.get(path, params={"phone": self.payload["customer_phone"]})
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["status"], "confirmed")

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
        edited = await self.client.put(f"/admin/services/{SERVICE}", json={
            "name": "New menu name", "duration_minutes": 60, "price_cents": 9999,
            "is_active": True,
        }, headers={"x-admin-key": self.env.ADMIN_API_KEY})
        self.assertEqual(edited.status_code, 200, edited.text)
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

    async def test_admin_catalog_requires_key(self):
        for resource, item_id, payload in (
            ("barbers", BARBER, {"name": "New barber"}),
            ("services", SERVICE, {"name": "New service", "duration_minutes": 30}),
        ):
            for method, path, body in (
                ("GET", f"/admin/{resource}", None),
                ("POST", f"/admin/{resource}", payload),
                ("PUT", f"/admin/{resource}/{item_id}", payload),
                ("DELETE", f"/admin/{resource}/{item_id}", None),
            ):
                for headers in ({}, {"x-admin-key": "wrong-key"}):
                    response = await self.client.request(method, path, json=body, headers=headers)
                    self.assertEqual(response.status_code, 401, response.text)
                self.env.ADMIN_API_KEY = None
                response = await self.client.request(method, path, json=body, headers={"x-admin-key": "a-key"})
                self.assertEqual(response.status_code, 503, response.text)
                self.env.ADMIN_API_KEY = "test-admin-key"
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM barbers"), 4)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM services"), 5)

    async def test_admin_calendar_defaults_to_today_and_accepts_long_ranges(self):
        headers = {"x-admin-key": self.env.ADMIN_API_KEY}
        created = await self.create()
        self.assertEqual(created.status_code, 201, created.text)
        today = datetime.now(settings_from_env(self.env).tz).date().isoformat()
        default = await self.client.get("/admin/bookings", headers=headers)
        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual((default.json()["from"], default.json()["to"]), (today, today))
        self.assertEqual(default.json()["bookings"], [])
        for start, end in ((self.day - timedelta(days=365), self.day),
                           (self.day, self.day + timedelta(days=365))):
            calendar = await self.client.get("/admin/bookings", params={
                "from": str(start), "to": str(end), "barber_id": BARBER,
                "include_cancelled": "false",
            }, headers=headers)
            self.assertEqual(calendar.status_code, 200, calendar.text)
            self.assertEqual([row["id"] for row in calendar.json()["bookings"]], [created.json()["id"]])
        for dates, code in (({"from": "2026-02-30"}, "INVALID_DATE"),
                            ({"from": str(self.day), "to": today}, "INVALID_DATE_RANGE")):
            rejected = await self.client.get("/admin/bookings", params=dates, headers=headers)
            self.assertEqual(rejected.status_code, 422, rejected.text)
            self.assertEqual(rejected.json()["error"]["code"], code)

    async def test_admin_barber_lifecycle_preserves_bookings(self):
        headers = {"x-admin-key": self.env.ADMIN_API_KEY}
        added = await self.client.post("/admin/barbers", json={"name": "  Barber #5  "}, headers=headers)
        self.assertEqual(added.status_code, 201, added.text)
        barber = added.json()
        self.assertEqual(barber["name"], "Barber #5")
        self.assertTrue(barber["is_active"])
        self.assertIn(barber["id"], [r["id"] for r in (await self.client.get("/barbers")).json()])
        created = await self.create(barber_id=barber["id"])
        self.assertEqual(created.status_code, 201, created.text)
        for _ in range(2):
            removed = await self.client.delete(f"/admin/barbers/{barber['id']}", headers=headers)
            self.assertEqual(removed.status_code, 200, removed.text)
            self.assertFalse(removed.json()["is_active"])
        self.assertNotIn(barber["id"], [r["id"] for r in (await self.client.get("/barbers")).json()])
        admin_list = await self.client.get("/admin/barbers", headers=headers)
        self.assertIn(removed.json(), admin_list.json())
        rejected = await self.create(barber_id=barber["id"], idempotency_key="inactive-barber-key")
        self.assertEqual(rejected.status_code, 404, rejected.text)
        self.assertEqual(rejected.json()["error"]["code"], "BARBER_NOT_FOUND")
        for path in ("/availability", "/schedule"):
            response = await self.client.get(path, params={
                "barber_id": barber["id"], "service_id": SERVICE, "date": str(self.day),
            })
            self.assertEqual(response.status_code, 404, response.text)
        retry = await self.create(barber_id=barber["id"])
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["id"], created.json()["id"])
        lookup = await self.client.get(f"/bookings/{created.json()['id']}", params={"phone": self.payload["customer_phone"]})
        self.assertEqual(lookup.json()["status"], "confirmed")
        calendar = await self.client.get("/admin/bookings", params={"from": str(self.day)}, headers=headers)
        self.assertEqual(calendar.json()["bookings"][0]["id"], created.json()["id"])
        cancelled = await self.client.post(f"/admin/bookings/{created.json()['id']}/cancel", json={}, headers=headers)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        restored = await self.client.put(f"/admin/barbers/{barber['id']}", json={"name": "Barber #5 renamed", "is_active": True}, headers=headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        rebooked = await self.create(barber_id=barber["id"], idempotency_key="restored-barber-key")
        self.assertEqual(rebooked.status_code, 201, rebooked.text)

    async def test_admin_service_lifecycle(self):
        headers = {"x-admin-key": self.env.ADMIN_API_KEY}
        menu = {"name": "  Haircut #6  ", "duration_minutes": 45, "price_cents": 2500}
        added = await self.client.post("/admin/services", json=menu, headers=headers)
        self.assertEqual(added.status_code, 201, added.text)
        service = added.json()
        self.assertEqual(service["name"], "Haircut #6")
        self.assertTrue(service["is_active"])
        self.assertIn(service["id"], [r["id"] for r in (await self.client.get("/services")).json()])
        created = await self.create(service_id=service["id"])
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["duration_minutes"], 45)
        self.assertEqual(created.json()["price_cents"], 2500)
        for _ in range(2):
            removed = await self.client.delete(f"/admin/services/{service['id']}", headers=headers)
            self.assertEqual(removed.status_code, 200, removed.text)
            self.assertFalse(removed.json()["is_active"])
        self.assertNotIn(service["id"], [r["id"] for r in (await self.client.get("/services")).json()])
        admin_list = await self.client.get("/admin/services", headers=headers)
        self.assertIn(removed.json(), admin_list.json())
        rejected = await self.create(service_id=service["id"], idempotency_key="inactive-service-key")
        self.assertEqual(rejected.status_code, 404, rejected.text)
        self.assertEqual(rejected.json()["error"]["code"], "SERVICE_NOT_FOUND")
        availability = await self.client.get("/availability", params={"barber_id": BARBER, "service_id": service["id"], "date": str(self.day)})
        self.assertEqual(availability.status_code, 404, availability.text)
        retry = await self.create(service_id=service["id"])
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json(), created.json())
        restored = await self.client.put(f"/admin/services/{service['id']}", json={
            "name": "Haircut #6 renamed", "duration_minutes": 60,
            "price_cents": 3000, "is_active": True,
        }, headers=headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        new_booking = await self.create(service_id=service["id"], starts_at=f"{self.day}T12:00", idempotency_key="restored-service-key")
        self.assertEqual(new_booking.status_code, 201, new_booking.text)
        self.assertEqual(new_booking.json()["duration_minutes"], 60)
        self.assertEqual(new_booking.json()["price_cents"], 3000)

    async def test_admin_catalog_validation_and_unknown_ids(self):
        headers = {"x-admin-key": self.env.ADMIN_API_KEY}
        for resource, valid, invalid in (
            ("barbers", {"name": "Barber"}, (
                {"name": " "}, {"name": "x" * 81}, {"name": None},
                {"is_active": "false"}, {"is_active": 0}, {"unexpected": True},
            )),
            ("services", {"name": "Service", "duration_minutes": 30}, (
                {"name": " "}, {"duration_minutes": 4}, {"duration_minutes": 241},
                {"duration_minutes": 30.5}, {"duration_minutes": True},
                {"price_cents": -1}, {"price_cents": 1.5}, {"price_cents": True},
                {"price_cents": 2147483648}, {"is_active": "false"}, {"unexpected": True},
            )),
        ):
            for changes in invalid:
                response = await self.client.post(f"/admin/{resource}", json={**valid, **changes}, headers=headers)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
            for method in ("PUT", "DELETE"):
                response = await self.client.request(method, f"/admin/{resource}/{uuid.uuid4()}", json=valid if method == "PUT" else None, headers=headers)
                self.assertEqual(response.status_code, 404, response.text)
                expected = "BARBER_NOT_FOUND" if resource == "barbers" else "SERVICE_NOT_FOUND"
                self.assertEqual(response.json()["error"]["code"], expected)
        for duration, price in ((5, 0), (240, 2147483647), (30, None)):
            response = await self.client.post("/admin/services", json={
                "name": "Unlisted", "duration_minutes": duration,
                "price_cents": price, "is_active": False,
            }, headers=headers)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertNotIn(response.json()["id"], [r["id"] for r in (await self.client.get("/services")).json()])

    async def test_booking_waits_for_concurrent_catalog_deactivation(self):
        for table, item_id, code in (("barbers", BARBER, "BARBER_NOT_FOUND"),
                                    ("services", SERVICE, "SERVICE_NOT_FOUND")):
            pending = None
            try:
                async with self.db.transaction():
                    await self.db.execute(f"UPDATE {table} SET is_active = FALSE WHERE id = $1", uuid.UUID(item_id))
                    pending = asyncio.create_task(self.create(idempotency_key=f"deactivation-{table}"))
                    async with asyncio.timeout(5):
                        while not pending.done():
                            await self.db.execute("SELECT pg_stat_clear_snapshot()")
                            blocked = await self.db.fetchval("""
                                SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                                WHERE datname = current_database() AND pid <> pg_backend_pid()
                                  AND wait_event_type = 'Lock')
                            """)
                            if blocked:
                                break
                            await asyncio.sleep(0.01)
                    self.assertFalse(pending.done(), "Booking must wait for the catalog update")
                response = await pending
                self.assertEqual(response.status_code, 404, response.text)
                self.assertEqual(response.json()["error"]["code"], code)
                self.assertEqual(await self.db.fetchval("SELECT count(*) FROM bookings"), 0)
            finally:
                if pending is not None:
                    await asyncio.gather(pending, return_exceptions=True)
                await self.db.execute(f"UPDATE {table} SET is_active = TRUE WHERE id = $1", uuid.UUID(item_id))

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

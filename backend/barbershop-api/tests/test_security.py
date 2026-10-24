import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from test_api import client_for


class Counter:
    def __init__(self, maximum):
        self.maximum = maximum
        self.counts = {}

    async def limit(self, options):
        key = options["key"]
        self.counts[key] = self.counts.get(key, 0) + 1
        return {"success": self.counts[key] <= self.maximum}


class Security(unittest.IsolatedAsyncioTestCase):
    async def test_booking_limit_groups_paths_queries_and_methods_by_ip(self):
        limiter = Counter(2)
        env = SimpleNamespace(SENSITIVE_RATE_LIMITER=limiter, ALLOWED_ORIGINS="https://allowed.invalid")
        async with client_for(env) as client:
            headers = {"cf-connecting-ip": "192.0.2.1", "origin": env.ALLOWED_ORIGINS}
            self.assertEqual((await client.get("/bookings/invalid?phone=123456", headers=headers)).status_code, 422)
            self.assertEqual((await client.post("/bookings/invalid/cancel", json={}, headers=headers)).status_code, 422)
            response = await client.get("/bookings/different?phone=654321", headers={**headers, "x-forwarded-for": "192.0.2.99"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json()["error"]["code"], "RATE_LIMITED")
            self.assertEqual(response.headers["retry-after"], "60")
            self.assertIn("Retry-After", response.headers["access-control-expose-headers"])
            self.assertEqual(response.headers["access-control-allow-origin"], env.ALLOWED_ORIGINS)
            self.assertEqual((await client.get("/bookings/invalid", headers={"cf-connecting-ip": "192.0.2.2"})).status_code, 422)
            self.assertEqual((await client.get("/shop", headers=headers)).status_code, 200)

    async def test_failed_admin_attempts_share_a_limit_but_valid_staff_can_work(self):
        limiter = Counter(2)
        env = SimpleNamespace(ADMIN_API_KEY="test-secret", SENSITIVE_RATE_LIMITER=limiter)
        async with client_for(env) as client:
            self.assertEqual((await client.get("/admin/services")).status_code, 401)
            self.assertEqual((await client.get("/admin/barbers", headers={"x-admin-key": "wrong"})).status_code, 401)
            self.assertEqual((await client.get("/admin/bookings", headers={"x-admin-key": "another"})).status_code, 429)
            # A valid key passes the auth-attempt gate; this unknown route needs no database.
            self.assertEqual((await client.get("/admin/unknown", headers={"x-admin-key": env.ADMIN_API_KEY})).status_code, 404)
            self.assertEqual((await client.get("/admin/services", headers=[(b"x-admin-key", b"\xff")])).status_code, 429)
        self.assertEqual(len(limiter.counts), 1)

    async def test_general_limit_and_missing_or_broken_bindings_fail_closed(self):
        async with client_for(SimpleNamespace(API_RATE_LIMITER=Counter(1))) as client:
            self.assertEqual((await client.get("/shop")).status_code, 200)
            self.assertEqual((await client.get("/different")).status_code, 429)
            preflight = await client.options("/shop", headers={"origin": "http://localhost:4321", "access-control-request-method": "GET"})
            self.assertEqual(preflight.status_code, 204)
        for binding in (None, SimpleNamespace(limit=AsyncMock(side_effect=RuntimeError("private detail")))):
            async with client_for(SimpleNamespace(API_RATE_LIMITER=binding)) as client:
                response = await client.get("/shop")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "RATE_LIMIT_UNAVAILABLE")
            self.assertNotIn("private detail", response.text)

    async def test_untrusted_origins_and_form_posts_never_reach_the_app(self):
        limiter = SimpleNamespace(limit=AsyncMock(return_value={"success": True}))
        env = SimpleNamespace(ALLOWED_ORIGINS="https://allowed.invalid", API_RATE_LIMITER=limiter)
        async with client_for(env) as client:
            for origin in ("https://evil.invalid", "null", "https://allowed.invalid.evil.invalid"):
                response = await client.post("/bookings", json={}, headers={"origin": origin})
                self.assertEqual(response.status_code, 403)
                self.assertNotIn("access-control-allow-origin", response.headers)
            for media in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
                response = await client.post("/bookings", content="{}", headers={"content-type": media})
                self.assertEqual(response.status_code, 415)
            for method, requested in (("PATCH", "content-type"), ("POST", "x-untrusted")):
                response = await client.options("/bookings", headers={"origin": env.ALLOWED_ORIGINS,
                    "access-control-request-method": method, "access-control-request-headers": requested})
                self.assertEqual(response.status_code, 403)
            limiter.limit.assert_not_awaited()
            self.assertEqual((await client.post("/bookings", json={})).status_code, 422)

    async def test_security_headers_cover_success_errors_and_unhandled_failures(self):
        env = SimpleNamespace(ALLOWED_ORIGINS="https://allowed.invalid")
        async with client_for(env, raise_app_exceptions=False) as client:
            responses = [await client.get("/shop"), await client.get("/missing"),
                         await client.get("/admin/services", headers=[(b"x-admin-key", b"\xff")])]
            with patch("catalog.settings_for", side_effect=RuntimeError("private detail")):
                response = await client.get("/shop", headers={"origin": env.ALLOWED_ORIGINS})
                self.assertEqual(response.status_code, 500)
                self.assertNotIn("private detail", response.text)
                self.assertEqual(response.headers["access-control-allow-origin"], env.ALLOWED_ORIGINS)
                responses.append(response)
            for response in responses:
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(response.headers["x-frame-options"], "DENY")
                self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                self.assertEqual(response.headers["strict-transport-security"], "max-age=31536000")
        async with client_for(SimpleNamespace(ADMIN_API_KEY="test-secret")) as client:
            self.assertEqual((await client.get("/admin/services", headers=[(b"x-admin-key", b"\xff")])).status_code, 401)

"""Run the real Python Worker locally against a newly created test database."""

import asyncio
import json
import os
import signal
import socket
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pyjson5

from support import ROOT, isolated_database
from config import settings_from_env
from types import SimpleNamespace


async def check_worker():
    async with isolated_database() as (db, dsn):
        state = ROOT / ".wrangler"
        state.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", prefix=".wrangler-smoke-", suffix=".json", dir=ROOT) as temporary:
            config = pyjson5.decode((ROOT / "wrangler.jsonc").read_text())
            config.update(name="barbershop-api-smoke", main=str(ROOT / "src/main.py"),
                          hyperdrive=[{"binding": "HYPERDRIVE", "id": "0" * 32}])
            config["vars"]["ALLOWED_ORIGINS"] = "https://allowed.invalid"
            config_path = Path(temporary.name)
            temporary.write(json.dumps(config))
            temporary.flush()
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            env = {**os.environ, "CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE": dsn,
                   "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
                   "WRANGLER_SEND_METRICS": "false"}
            log_path = state / "worker-smoke.log"
            with log_path.open("w") as log:
                process = await asyncio.create_subprocess_exec(
                    str(Path(sys.executable).parent / "pywrangler"), "dev", "--local",
                    "--ip", "127.0.0.1", "--port", str(port), "--inspector-port", "0",
                    "--var", "ADMIN_API_KEY:worker-smoke-admin",
                    "--config", str(config_path), cwd=ROOT, env=env,
                    stdout=log, stderr=log, start_new_session=True,
                )
                try:
                    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
                        deadline = asyncio.get_running_loop().time() + 240
                        while asyncio.get_running_loop().time() < deadline:
                            if process.returncode is not None:
                                raise RuntimeError("Worker exited before becoming ready")
                            try:
                                response = await client.get("/")
                                assert response.status_code == 200, response.text
                                break
                            except httpx.TransportError:
                                pass
                            await asyncio.sleep(0.25)
                        else:
                            raise TimeoutError("Worker did not become ready within 240 seconds")
                        response = await client.get("/health")
                        assert response.status_code == 200, response.text
                        admin_headers = {"x-admin-key": "worker-smoke-admin"}
                        catalog = (("barbers", {"name": "Smoke Barber"}),
                                   ("services", {"name": "Smoke Service", "duration_minutes": 30,
                                                 "price_cents": 1500}))
                        catalog_ids = {}
                        for resource, data in catalog:
                            response = await client.get(f"/admin/{resource}")
                            assert response.status_code == 401, response.text
                            response = await client.post(f"/admin/{resource}", json=data, headers=admin_headers)
                            assert response.status_code == 201, response.text
                            catalog_ids[resource] = response.json()["id"]
                        day = datetime.now(settings_from_env(SimpleNamespace()).tz).date() + timedelta(days=7)
                        while day.weekday() == 6:
                            day += timedelta(days=1)
                        payload = dict(barber_id=catalog_ids["barbers"],
                                       service_id=catalog_ids["services"],
                                       starts_at=f"{day}T10:00", customer_name="Worker Test",
                                       customer_phone="+306900000001", idempotency_key="worker-smoke-key")
                        created = await client.post("/bookings", json=payload)
                        assert created.status_code == 201, created.text
                        retry = await client.post("/bookings", json=payload)
                        assert retry.status_code == 200 and retry.json()["id"] == created.json()["id"], retry.text
                        conflict = await client.post("/bookings", json={**payload, "customer_phone": "+306900000099"})
                        assert conflict.status_code == 409, conflict.text
                        prefix = json.dumps(payload)[:-1].encode() + b',"padding":"'
                        for size, expected in ((65536, 200), (65537, 413)):
                            body = prefix + b"x" * (size - len(prefix) - 2) + b'"}'
                            async def chunks():
                                for offset in range(0, len(body), 1024):
                                    yield body[offset:offset + 1024]
                            response = await client.post("/bookings", content=chunks(), headers={
                                "content-type": "application/json", "origin": "https://allowed.invalid"})
                            assert response.status_code == expected, response.text
                            assert response.headers["access-control-allow-origin"] == "https://allowed.invalid"
                        for resource, data in catalog:
                            item_id = catalog_ids[resource]
                            path = f"/admin/{resource}/{item_id}"
                            for method in ("PUT", "DELETE"):
                                response = await client.options(path, headers={
                                    "origin": "https://allowed.invalid",
                                    "access-control-request-method": method,
                                    "access-control-request-headers": "content-type,x-admin-key"})
                                assert method in response.headers["access-control-allow-methods"], response.text
                            response = await client.delete(path, headers=admin_headers)
                            assert response.status_code == 200 and not response.json()["is_active"], response.text
                            public = await client.get(f"/{resource}")
                            assert item_id not in [r["id"] for r in public.json()], public.text
                            admin_list = await client.get(f"/admin/{resource}", headers=admin_headers)
                            assert response.json() in admin_list.json(), admin_list.text
                            retry = await client.post("/bookings", json=payload)
                            assert retry.status_code == 200 and retry.json()["id"] == created.json()["id"], retry.text
                            rejected = await client.post("/bookings", json={**payload, "idempotency_key": f"inactive-{resource}"})
                            assert rejected.status_code == 404, rejected.text
                            response = await client.put(path, json={**data, "name": data["name"] + " edited", "is_active": True}, headers=admin_headers)
                            assert response.status_code == 200 and response.json()["is_active"], response.text
                        assert await db.fetchval("SELECT count(*) FROM bookings") == 1
                except BaseException:
                    print(log_path.read_text().replace(dsn, "<test-database>"), file=sys.stderr)
                    raise
                finally:
                    if process.returncode is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            await asyncio.wait_for(process.wait(), timeout=10)
                        except TimeoutError:
                            os.killpg(process.pid, signal.SIGKILL)
                            await process.wait()
    print("Workers smoke checks passed: database, admin catalog, create/retry/conflict, streamed 64 KiB boundary, CORS.")


if __name__ == "__main__":
    asyncio.run(check_worker())

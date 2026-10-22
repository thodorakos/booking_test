"""Catalog & meta routes: root info, health check, barbers, services."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api_models import BarberOut, HealthOut, ServiceInfo, ServiceOut
from config import settings_for
from db import db_connection
from errors import log_event

router = APIRouter(tags=["catalog"])

API_VERSION = "1.0.0"


@router.get("/shop", summary="Public shop time zone and booking policy")
async def shop_info(request: Request):
    st = settings_for(request)
    return {
        "timezone": st.tz_name,
        "currency": "EUR",
        "open_time": st.open_time.strftime("%H:%M"),
        "close_time": st.close_time.strftime("%H:%M"),
        "closed_weekdays": sorted(st.closed_weekdays),
        "booking_horizon_days": st.horizon_days,
        "booking_lead_minutes": st.lead_minutes,
        "cancel_cutoff_hours": st.cancel_cutoff_hours,
    }


@router.get("/", response_model=ServiceInfo, summary="Service banner")
async def root():
    return ServiceInfo(service="barbershop-api", version=API_VERSION, docs="/docs")


@router.get("/health", summary="Liveness + database reachability")
async def health(request: Request):
    st = settings_for(request)
    try:
        async with db_connection(request) as conn:
            await conn.fetchval("SELECT 1", timeout=st.query_timeout)
    except Exception as exc:
        log_event("healthcheck_failed", detail=str(exc))
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unreachable", "version": API_VERSION},
        )
    return HealthOut(status="ok", database="ok", version=API_VERSION)


@router.get("/barbers", response_model=list[BarberOut], summary="List active barbers")
async def list_barbers(request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        rows = await conn.fetch(
            "SELECT id, name FROM barbers WHERE is_active ORDER BY name",
            timeout=st.query_timeout,
        )
    return [BarberOut(id=row["id"], name=row["name"]) for row in rows]


@router.get("/services", response_model=list[ServiceOut], summary="List active services")
async def list_services(request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        rows = await conn.fetch(
            "SELECT id, name, duration_minutes, price_cents FROM services "
            "WHERE is_active ORDER BY duration_minutes, name",
            timeout=st.query_timeout,
        )
    return [
        ServiceOut(
            id=row["id"],
            name=row["name"],
            duration_minutes=row["duration_minutes"],
            price_cents=row["price_cents"],
        )
        for row in rows
    ]

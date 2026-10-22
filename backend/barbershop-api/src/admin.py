"""Admin routes (X-Admin-Key header required):

- GET  /admin/bookings      day-range calendar with full customer details
- POST /admin/bookings/{id}/cancel   cancel any booking, no cutoff
- GET/POST/PUT/DELETE /admin/barbers and /admin/services   manage the catalog

The key is a single shop secret set via `wrangler secret put ADMIN_API_KEY`
(ADMIN_DISABLED 503 until it exists). Comparison is constant-time.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Request

from api_models import (
    AdminBarberOut,
    AdminBookingsOut,
    AdminCancelRequest,
    AdminServiceOut,
    BarberInput,
    BookingOut,
    ServiceInput,
    booking_out,
)
from bookings import SQL_BOOKING_SELECT
from config import settings_for
from db import db_connection
from errors import ApiError, log_event
from security import require_admin as _require_admin
from timeutils import local_today, naive_to_utc, parse_date_strict

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_require_admin)])


@router.get("/barbers", response_model=list[AdminBarberOut],
            summary="List all barbers, including inactive ones")
async def list_barbers(request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        rows = await conn.fetch(
            "SELECT id, name, is_active FROM barbers ORDER BY name, id",
            timeout=st.query_timeout,
        )
    return [dict(row) for row in rows]


@router.post("/barbers", status_code=201, response_model=AdminBarberOut,
             summary="Add a barber")
async def create_barber(payload: BarberInput, request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        row = await conn.fetchrow(
            "INSERT INTO barbers (name, is_active) VALUES ($1, $2) "
            "RETURNING id, name, is_active",
            payload.name, payload.is_active, timeout=st.query_timeout,
        )
    log_event("barber_created", barber_id=str(row["id"]), is_active=row["is_active"])
    return dict(row)


@router.put("/barbers/{barber_id}", response_model=AdminBarberOut,
            summary="Replace a barber's name and active status")
async def update_barber(barber_id: uuid.UUID, payload: BarberInput, request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        row = await conn.fetchrow(
            "UPDATE barbers SET name = $2, is_active = $3 WHERE id = $1 "
            "RETURNING id, name, is_active",
            barber_id, payload.name, payload.is_active, timeout=st.query_timeout,
        )
    if row is None:
        raise ApiError(404, "BARBER_NOT_FOUND", "No barber with that id.")
    log_event("barber_updated", barber_id=str(barber_id), is_active=row["is_active"])
    return dict(row)


@router.delete("/barbers/{barber_id}", response_model=AdminBarberOut,
               summary="Deactivate a barber; preserve existing appointments")
async def remove_barber(barber_id: uuid.UUID, request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        row = await conn.fetchrow(
            "UPDATE barbers SET is_active = FALSE WHERE id = $1 "
            "RETURNING id, name, is_active",
            barber_id, timeout=st.query_timeout,
        )
    if row is None:
        raise ApiError(404, "BARBER_NOT_FOUND", "No barber with that id.")
    log_event("barber_deactivated", barber_id=str(barber_id))
    return dict(row)


@router.get("/services", response_model=list[AdminServiceOut],
            summary="List all services, including inactive ones")
async def list_services(request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        rows = await conn.fetch(
            "SELECT id, name, duration_minutes, price_cents, is_active FROM services "
            "ORDER BY duration_minutes, name, id",
            timeout=st.query_timeout,
        )
    return [dict(row) for row in rows]


@router.post("/services", status_code=201, response_model=AdminServiceOut,
             summary="Add a service")
async def create_service(payload: ServiceInput, request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        row = await conn.fetchrow(
            "INSERT INTO services (name, duration_minutes, price_cents, is_active) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id, name, duration_minutes, price_cents, is_active",
            payload.name, payload.duration_minutes, payload.price_cents, payload.is_active,
            timeout=st.query_timeout,
        )
    log_event("service_created", service_id=str(row["id"]), is_active=row["is_active"])
    return dict(row)


@router.put("/services/{service_id}", response_model=AdminServiceOut,
            summary="Replace a service's name, duration, price and active status")
async def update_service(service_id: uuid.UUID, payload: ServiceInput, request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        row = await conn.fetchrow(
            "UPDATE services SET name = $2, duration_minutes = $3, price_cents = $4, "
            "is_active = $5 WHERE id = $1 "
            "RETURNING id, name, duration_minutes, price_cents, is_active",
            service_id, payload.name, payload.duration_minutes, payload.price_cents,
            payload.is_active, timeout=st.query_timeout,
        )
    if row is None:
        raise ApiError(404, "SERVICE_NOT_FOUND", "No service with that id.")
    log_event("service_updated", service_id=str(service_id), is_active=row["is_active"])
    return dict(row)


@router.delete("/services/{service_id}", response_model=AdminServiceOut,
               summary="Deactivate a service; preserve existing appointments")
async def remove_service(service_id: uuid.UUID, request: Request):
    st = settings_for(request)
    async with db_connection(request) as conn:
        row = await conn.fetchrow(
            "UPDATE services SET is_active = FALSE WHERE id = $1 "
            "RETURNING id, name, duration_minutes, price_cents, is_active",
            service_id, timeout=st.query_timeout,
        )
    if row is None:
        raise ApiError(404, "SERVICE_NOT_FOUND", "No service with that id.")
    log_event("service_deactivated", service_id=str(service_id))
    return dict(row)


@router.get("/bookings", response_model=AdminBookingsOut,
            summary="List bookings in a date range (full customer details)")
async def list_bookings(
    request: Request,
    date_from: str | None = Query(None, alias="from", description="YYYY-MM-DD; default today"),
    date_to: str | None = Query(None, alias="to", description="YYYY-MM-DD; default = from"),
    barber_id: uuid.UUID | None = Query(None, description="Optional filter"),
    include_cancelled: bool = Query(True, description="Include cancelled bookings"),
):
    st = settings_for(request)
    today = local_today(st.tz)

    try:
        d_from = parse_date_strict(date_from) if date_from else today
        d_to = parse_date_strict(date_to) if date_to else d_from
    except ValueError as exc:
        raise ApiError(422, "INVALID_DATE", str(exc)) from None

    if d_from > d_to:
        raise ApiError(422, "INVALID_DATE_RANGE", "'from' must not be after 'to'.")

    # Inclusive local-day bounds converted to UTC instants.
    range_start = naive_to_utc(datetime.combine(d_from, time.min), st.tz)
    range_end = naive_to_utc(datetime.combine(d_to + timedelta(days=1), time.min), st.tz)

    clauses = ["bk.starts_at >= $1", "bk.starts_at < $2"]
    params: list = [range_start, range_end]
    if barber_id is not None:
        clauses.append(f"bk.barber_id = ${len(params) + 1}")
        params.append(barber_id)
    if not include_cancelled:
        clauses.append("bk.status = 'confirmed'")

    sql = SQL_BOOKING_SELECT + "WHERE " + " AND ".join(clauses) + " ORDER BY bk.starts_at"

    async with db_connection(request) as conn:
        rows = await conn.fetch(sql, *params, timeout=st.query_timeout)

    out = [booking_out(row, st.tz) for row in rows]
    return AdminBookingsOut.model_validate(
        {
            "from": d_from.isoformat(),
            "to": d_to.isoformat(),
            "barber_id": barber_id,
            "include_cancelled": include_cancelled,
            "count": len(out),
            "bookings": out,
        }
    )


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut,
             summary="Cancel any booking (shop override, no cutoff)")
async def admin_cancel_booking(
    booking_id: uuid.UUID, payload: AdminCancelRequest, request: Request
):
    from bookings import SQL_BOOKING_BY_ID, SQL_CANCEL_BOOKING

    st = settings_for(request)

    async with db_connection(request) as conn:
        row = await conn.fetchrow(SQL_BOOKING_BY_ID, booking_id, timeout=st.query_timeout)
        if row is None:
            raise ApiError(404, "BOOKING_NOT_FOUND", "No booking with that id.")
        if row["status"] != "confirmed":
            raise ApiError(409, "ALREADY_CANCELLED", "This booking is already cancelled.")

        updated = await conn.fetchrow(
            SQL_CANCEL_BOOKING,
            booking_id,
            payload.reason or "cancelled by shop",
            timeout=st.query_timeout,
        )
        if updated is None:  # cancelled concurrently
            raise ApiError(409, "ALREADY_CANCELLED", "This booking was just cancelled.")

    log_event(
        "booking_cancelled",
        booking_id=str(booking_id),
        by="admin",
        reason=payload.reason,
    )
    return booking_out(updated, st.tz)

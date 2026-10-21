"""Admin routes (X-Admin-Key header required):

- GET  /admin/bookings      day-range calendar with full customer details
- POST /admin/bookings/{id}/cancel   cancel any booking, no cutoff

The key is a single shop secret set via `wrangler secret put ADMIN_API_KEY`
(ADMIN_DISABLED 503 until it exists). Comparison is constant-time.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Request

from api_models import AdminBookingsOut, AdminCancelRequest, BookingOut, booking_out
from bookings import SQL_BOOKING_SELECT
from config import settings_for
from db import db_connection
from errors import ApiError, log_event
from security import require_admin as _require_admin
from timeutils import local_today, naive_to_utc, parse_date_strict

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_require_admin)])

MAX_RANGE_DAYS = 31


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
    if (d_to - d_from).days > MAX_RANGE_DAYS:
        raise ApiError(422, "INVALID_DATE_RANGE", f"Range is limited to {MAX_RANGE_DAYS} days.")

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

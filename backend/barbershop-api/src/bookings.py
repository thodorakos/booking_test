"""Bookings: creation (with idempotency), lookup, cancellation,
availability and the public day schedule.

Creation flow, in order:
1. shape/format validation (Pydantic) + idempotency replay check;
2. time rules for new bookings: closed weekday, horizon, grid alignment;
3. barber + service lookup (404s for unknown or deactivated rows);
4. opening-hours fit (needs the service duration);
5. DST-safe wall->UTC conversion, then lead-time check;
6. single INSERT; Postgres is the final authority:
   - exclusion violation (23P01)  -> 409 SLOT_TAKEN
   - unique violation on the idempotency key (23505, race) -> replay the
     original booking instead of erroring.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api_models import (
    AvailabilityOut,
    BookingCreate,
    BookingOut,
    CancelBookingRequest,
    IDEMPOTENCY_RE,
    ScheduleBookingOut,
    ScheduleOut,
    SlotOut,
    booking_out,
)
from availability import compute_slots, day_window
from config import settings_for
from db import db_connection
from errors import ApiError, log_event
from security import admin_key_valid, phone_matches
from timeutils import (
    WallClockError,
    local_today,
    naive_to_utc,
    parse_date_strict,
    parse_wall_strict,
    utc_iso,
    utc_to_wall,
)

router = APIRouter(tags=["bookings"])

# ---------------------------------------------------------------- SQL

_BOOKING_COLUMNS = """
    bk.id, bk.barber_id, bk.service_id, bk.starts_at, bk.ends_at,
    bk.customer_name, bk.customer_phone, bk.notes, bk.status,
    bk.idempotency_key, bk.request_fingerprint, bk.price_cents,
    bk.cancellation_reason, bk.cancelled_at, bk.created_at
"""

SQL_BOOKING_SELECT = f"""
SELECT {_BOOKING_COLUMNS},
       b.name AS barber_name, s.name AS service_name
FROM bookings bk
JOIN barbers b ON b.id = bk.barber_id
JOIN services s ON s.id = bk.service_id
"""

SQL_BOOKING_BY_ID = SQL_BOOKING_SELECT + "WHERE bk.id = $1"

SQL_BOOKING_BY_IDEMPOTENCY = SQL_BOOKING_SELECT + "WHERE bk.idempotency_key = $1"

SQL_CATALOG_PAIR = """
SELECT b.id AS barber_id, b.name AS barber_name, b.is_active AS barber_active,
       s.id AS service_id, s.name AS service_name, s.is_active AS service_active,
       s.duration_minutes, s.price_cents
FROM barbers b LEFT JOIN services s ON s.id = $2
WHERE b.id = $1
"""

SQL_INSERT_BOOKING = """
WITH ins AS (
    INSERT INTO bookings (barber_id, service_id, starts_at, ends_at,
                          customer_name, customer_phone, notes, idempotency_key,
                          price_cents, request_fingerprint)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id, barber_id, service_id, starts_at, ends_at, customer_name,
              customer_phone, notes, status, idempotency_key,
              cancellation_reason, cancelled_at, created_at, price_cents
)
SELECT ins.id, ins.barber_id, ins.service_id, ins.starts_at, ins.ends_at,
       ins.customer_name, ins.customer_phone, ins.notes, ins.status,
       ins.idempotency_key, ins.cancellation_reason, ins.cancelled_at,
       ins.created_at, ins.price_cents,
       b.name AS barber_name, s.name AS service_name
FROM ins
JOIN barbers b ON b.id = ins.barber_id
JOIN services s ON s.id = ins.service_id
"""

SQL_CANCEL_BOOKING = """
WITH upd AS (
    UPDATE bookings
    SET status = 'cancelled', cancelled_at = now(), cancellation_reason = $2
    WHERE id = $1 AND status = 'confirmed'
    RETURNING id, barber_id, service_id, starts_at, ends_at, customer_name,
              customer_phone, notes, status, idempotency_key,
              cancellation_reason, cancelled_at, created_at, price_cents
)
SELECT upd.id, upd.barber_id, upd.service_id, upd.starts_at, upd.ends_at,
       upd.customer_name, upd.customer_phone, upd.notes, upd.status,
       upd.idempotency_key, upd.cancellation_reason, upd.cancelled_at,
       upd.created_at, upd.price_cents,
       b.name AS barber_name, s.name AS service_name
FROM upd
JOIN barbers b ON b.id = upd.barber_id
JOIN services s ON s.id = upd.service_id
"""

SQL_DAY_BUSY = """
SELECT starts_at, ends_at FROM bookings
WHERE barber_id = $1 AND status = 'confirmed'
  AND tstzrange(starts_at, ends_at) && tstzrange($2::timestamptz, $3::timestamptz)
ORDER BY starts_at
"""

SQL_DAY_SCHEDULE = """
SELECT bk.starts_at, bk.ends_at, bk.status, s.name AS service_name
FROM bookings bk
JOIN services s ON s.id = bk.service_id
WHERE bk.barber_id = $1
  AND tstzrange(bk.starts_at, bk.ends_at) && tstzrange($2::timestamptz, $3::timestamptz)
ORDER BY bk.starts_at
"""

# Window buffer around the day: catches bookings that (pathologically) start
# on an adjacent day but reach into this one.
DAY_WINDOW_BUFFER = timedelta(hours=2)


# ---------------------------------------------------------------- helpers


def _parse_date_or_422(value: str):
    try:
        return parse_date_strict(value)
    except ValueError as exc:
        raise ApiError(422, "INVALID_DATE", str(exc)) from None


def _idempotency_key_from(payload: BookingCreate, request: Request) -> str | None:
    if payload.idempotency_key:
        return payload.idempotency_key
    header = request.headers.get("idempotency-key")
    if header is None:
        return None
    header = header.strip()
    if not IDEMPOTENCY_RE.fullmatch(header):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Idempotency-Key header must be 8-100 chars of A-Z a-z 0-9 . _ : -",
        )
    return header


def _replay_response(row, fingerprint: str, tz) -> JSONResponse:
    if row["request_fingerprint"] != fingerprint:
        raise ApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "This idempotency key cannot be used for this request.",
        )
    return JSONResponse(
        status_code=200,
        content=booking_out(row, tz).model_dump(mode="json"),
        headers={"Idempotent-Replay": "true"},
    )


# ---------------------------------------------------------------- routes


@router.post("/bookings", status_code=201, response_model=BookingOut,
             summary="Create a booking")
async def create_booking(payload: BookingCreate, request: Request):
    st = settings_for(request)
    now = datetime.now(timezone.utc)
    idem = _idempotency_key_from(payload, request)
    fingerprint = hashlib.sha256(json.dumps(
        payload.model_dump(mode="json", exclude={"idempotency_key"}), sort_keys=True
    ).encode()).hexdigest()

    # -- 1. wall-clock format ------------------------------------------------
    try:
        wall = parse_wall_strict(payload.starts_at)
    except WallClockError as exc:
        raise ApiError(422, "INVALID_START_TIME", f"Invalid starts_at: {exc}") from None

    async with db_connection(request) as conn:
        # -- 1b. idempotent replay --------------------------------------------
        if idem:
            existing = await conn.fetchrow(
                SQL_BOOKING_BY_IDEMPOTENCY, idem, timeout=st.query_timeout
            )
            if existing is not None:
                return _replay_response(existing, fingerprint, st.tz)

        # Existing requests replay even when shop policy has changed.
        day = wall.date()
        if day.weekday() in st.closed_weekdays:
            raise ApiError(422, "CLOSED_DAY", "The shop is closed on that weekday.")
        today = local_today(st.tz)
        if day > today + timedelta(days=st.horizon_days):
            raise ApiError(
                422,
                "TOO_FAR_AHEAD",
                f"Bookings open at most {st.horizon_days} days ahead "
                f"(currently until {today + timedelta(days=st.horizon_days):%Y-%m-%d}).",
            )
        if wall.minute % st.grid_minutes != 0 or wall.second != 0:
            raise ApiError(
                422,
                "SLOT_NOT_ALIGNED",
                f"Start times must align to {st.grid_minutes}-minute boundaries "
                f"(e.g. 10:00 or 10:30).",
            )

        # -- 3. barber + service ------------------------------------------------
        pair = await conn.fetchrow(
            SQL_CATALOG_PAIR,
            payload.barber_id,
            payload.service_id,
            timeout=st.query_timeout,
        )
        if pair is None or not pair["barber_active"]:
            raise ApiError(
                404, "BARBER_NOT_FOUND", f"No active barber with id {payload.barber_id}."
            )
        if not pair["service_active"]:
            raise ApiError(
                404, "SERVICE_NOT_FOUND", f"No active service with id {payload.service_id}."
            )
        duration = pair["duration_minutes"]

        # -- 4. opening hours ----------------------------------------------------
        wall_end = wall + timedelta(minutes=duration)
        if (
            wall.time() < st.open_time
            or wall_end.time() > st.close_time
            or wall_end.date() != day
        ):
            raise ApiError(
                422,
                "OUTSIDE_OPENING_HOURS",
                f"Bookings must start at or after {st.open_time:%H:%M} and end "
                f"by {st.close_time:%H:%M} local time.",
            )

        # -- 5. DST-safe conversion + lead time ----------------------------------
        try:
            start_utc = naive_to_utc(wall, st.tz)
        except WallClockError as exc:
            raise ApiError(422, "INVALID_START_TIME", str(exc)) from None
        end_utc = start_utc + timedelta(minutes=duration)

        if start_utc < now + timedelta(minutes=st.lead_minutes):
            raise ApiError(
                422,
                "TOO_LATE_TO_BOOK",
                f"Bookings need at least {st.lead_minutes} minutes of lead time.",
            )

        # -- 6. INSERT; the DB constraint is the final authority -----------------
        try:
            row = await conn.fetchrow(
                SQL_INSERT_BOOKING,
                payload.barber_id,
                payload.service_id,
                start_utc,
                end_utc,
                payload.customer_name,
                payload.customer_phone,
                payload.notes,
                idem,
                pair["price_cents"],
                fingerprint,
                timeout=st.query_timeout,
            )
        except asyncpg.PostgresError as exc:
            # Two clients raced with the SAME idempotency key: the second one
            # replays the winner's booking instead of failing.
            if idem and getattr(exc, "sqlstate", None) == "23505":
                existing = await conn.fetchrow(
                    SQL_BOOKING_BY_IDEMPOTENCY, idem, timeout=st.query_timeout
                )
                if existing is not None:
                    return _replay_response(existing, fingerprint, st.tz)
            raise  # 23P01 -> 409 SLOT_TAKEN via the global handler

    log_event(
        "booking_created",
        booking_id=str(row["id"]),
        barber_id=str(payload.barber_id),
        service_id=str(payload.service_id),
        starts_at=utc_iso(row["starts_at"]),
    )
    return booking_out(row, st.tz)


@router.get("/bookings/{booking_id}", response_model=BookingOut,
            summary="Fetch a booking (owner phone or admin key)")
async def get_booking(booking_id: uuid.UUID, request: Request, phone: str | None = None):
    st = settings_for(request)
    is_admin = admin_key_valid(request, st)

    async with db_connection(request) as conn:
        row = await conn.fetchrow(SQL_BOOKING_BY_ID, booking_id, timeout=st.query_timeout)

    if row is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "No booking with that id.")
    if not is_admin:
        if not phone:
            raise ApiError(
                401,
                "PHONE_REQUIRED",
                "Provide the booking's phone number as the 'phone' query parameter, "
                "or an X-Admin-Key header.",
            )
        if not phone_matches(phone, row["customer_phone"]):
            raise ApiError(401, "PHONE_MISMATCH", "That phone number does not match this booking.")
    return booking_out(row, st.tz)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut,
             summary="Cancel a booking (owner phone, before the cutoff)")
async def cancel_booking(booking_id: uuid.UUID, payload: CancelBookingRequest, request: Request):
    st = settings_for(request)
    now = datetime.now(timezone.utc)

    async with db_connection(request) as conn:
        row = await conn.fetchrow(SQL_BOOKING_BY_ID, booking_id, timeout=st.query_timeout)
        if row is None:
            raise ApiError(404, "BOOKING_NOT_FOUND", "No booking with that id.")
        if row["status"] != "confirmed":
            raise ApiError(409, "ALREADY_CANCELLED", "This booking is already cancelled.")

        if not phone_matches(payload.phone, row["customer_phone"]):
            raise ApiError(
                401, "PHONE_MISMATCH", "That phone number does not match this booking."
            )

        if row["starts_at"] - now < timedelta(hours=st.cancel_cutoff_hours):
            raise ApiError(
                422,
                "TOO_LATE_TO_CANCEL",
                f"Free cancellation ends {st.cancel_cutoff_hours}h before the "
                f"appointment; contact the shop and an admin can still cancel.",
            )

        # WHERE status='confirmed' guard: if another request cancels it
        # concurrently between the checks above and this UPDATE, we get no
        # row back and report ALREADY_CANCELLED instead of double-cancelling.
        updated = await conn.fetchrow(
            SQL_CANCEL_BOOKING, booking_id, "customer", timeout=st.query_timeout
        )
        if updated is None:
            raise ApiError(409, "ALREADY_CANCELLED", "This booking was just cancelled.")

    log_event("booking_cancelled", booking_id=str(booking_id), by="customer")
    return booking_out(updated, st.tz)


@router.get("/availability", response_model=AvailabilityOut,
            summary="Bookable start times for a barber/service/day")
async def get_availability(
    barber_id: uuid.UUID, service_id: uuid.UUID, date: str, request: Request
):
    day = _parse_date_or_422(date)
    st = settings_for(request)
    now = datetime.now(timezone.utc)

    async with db_connection(request) as conn:
        barber = await conn.fetchrow(
            "SELECT name, is_active FROM barbers WHERE id = $1",
            barber_id,
            timeout=st.query_timeout,
        )
        if barber is None or not barber["is_active"]:
            raise ApiError(404, "BARBER_NOT_FOUND", f"No active barber with id {barber_id}.")
        service = await conn.fetchrow(
            "SELECT name, duration_minutes, is_active FROM services WHERE id = $1",
            service_id,
            timeout=st.query_timeout,
        )
        if service is None or not service["is_active"]:
            raise ApiError(404, "SERVICE_NOT_FOUND", f"No active service with id {service_id}.")

        slots: list[datetime] = []
        window = day_window(day, st)
        if window is not None:
            open_utc, close_utc = window
            busy_rows = await conn.fetch(
                SQL_DAY_BUSY,
                barber_id,
                open_utc - DAY_WINDOW_BUFFER,
                close_utc + DAY_WINDOW_BUFFER,
                timeout=st.query_timeout,
            )
            busy = [(r["starts_at"], r["ends_at"]) for r in busy_rows]
            slots = compute_slots(day, service["duration_minutes"], busy, now, st)
            if day > local_today(st.tz) + timedelta(days=st.horizon_days):
                slots = []  # beyond the booking horizon: nothing offered

    return AvailabilityOut(
        barber_id=barber_id,
        barber_name=barber["name"],
        service_id=service_id,
        service_name=service["name"],
        date=day.isoformat(),
        duration_minutes=service["duration_minutes"],
        closed=window is None,
        available=[
            SlotOut(starts_at=utc_iso(slot), starts_at_local=utc_to_wall(slot, st.tz))
            for slot in slots
        ],
    )


@router.get("/schedule", response_model=ScheduleOut,
            summary="Public day calendar for a barber (no customer PII)")
async def get_schedule(barber_id: uuid.UUID, date: str, request: Request):
    day = _parse_date_or_422(date)
    st = settings_for(request)

    async with db_connection(request) as conn:
        barber = await conn.fetchrow(
            "SELECT name, is_active FROM barbers WHERE id = $1",
            barber_id,
            timeout=st.query_timeout,
        )
        if barber is None or not barber["is_active"]:
            raise ApiError(404, "BARBER_NOT_FOUND", f"No active barber with id {barber_id}.")

        entries: list[ScheduleBookingOut] = []
        window = day_window(day, st)
        if window is not None:
            open_utc, close_utc = window
            rows = await conn.fetch(
                SQL_DAY_SCHEDULE,
                barber_id,
                open_utc - DAY_WINDOW_BUFFER,
                close_utc + DAY_WINDOW_BUFFER,
                timeout=st.query_timeout,
            )
            entries = [
                ScheduleBookingOut(
                    starts_at=utc_iso(r["starts_at"]),
                    ends_at=utc_iso(r["ends_at"]),
                    starts_at_local=utc_to_wall(r["starts_at"], st.tz),
                    ends_at_local=utc_to_wall(r["ends_at"], st.tz),
                    service_name=r["service_name"],
                    status=r["status"],
                )
                for r in rows
            ]

    return ScheduleOut(
        barber_id=barber_id,
        barber_name=barber["name"],
        date=day.isoformat(),
        closed=window is None,
        bookings=entries,
    )

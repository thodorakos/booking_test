"""Pydantic v2 models — the API's wire contract.

Request models validate leniently-formatted input (phones are normalized to
digits-plus-optional-leading-plus). Response models return every timestamp in
two forms: absolute UTC ("starts_at": "2026-10-25T11:00:00Z") and shop-local
wall time ("starts_at_local": "2026-10-25T14:00"), so the frontend never has
to do timezone math.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from timeutils import utc_iso, utc_iso_opt, utc_to_wall

_PHONE_CLEAN = re.compile(r"[\s\-().]")
_PHONE_OK = re.compile(r"\+?[0-9]{6,15}")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,100}$")


def normalize_phone(value: str) -> str:
    """Strip spacing/punctuation; validate 6-15 digits with optional '+'."""
    cleaned = _PHONE_CLEAN.sub("", value or "")
    if not _PHONE_OK.fullmatch(cleaned):
        raise ValueError(
            "customer_phone must contain 6-15 digits, optionally starting "
            "with '+' (e.g. +306912345678)"
        )
    return cleaned


# ---------------------------------------------------------------- requests


class BookingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    barber_id: uuid.UUID
    service_id: uuid.UUID
    starts_at: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$",
        description="Shop-local wall time, e.g. 2026-10-25T14:00",
        examples=["2026-10-25T14:00"],
    )
    customer_name: str = Field(min_length=1, max_length=80)
    customer_phone: str = Field(min_length=5, max_length=24)
    notes: Optional[str] = Field(default=None, max_length=500)
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9._:-]{8,100}$",
        description="Optional client-generated key; retries with the same key "
        "with the same payload return the original booking. Changed payloads get 409.",
    )

    @field_validator("customer_phone")
    @classmethod
    def _normalize_customer_phone(cls, value: str) -> str:
        return normalize_phone(value)


class CancelBookingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    phone: str = Field(min_length=5, max_length=24)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        return normalize_phone(value)


class AdminCancelRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: Optional[str] = Field(default=None, max_length=200)


class BarberInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class ServiceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=80)
    duration_minutes: int = Field(ge=5, le=240)
    price_cents: Optional[int] = Field(default=None, ge=0, le=2147483647)
    is_active: bool = True


# ---------------------------------------------------------------- responses


class BarberOut(BaseModel):
    id: uuid.UUID
    name: str


class ServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    duration_minutes: int
    price_cents: Optional[int] = None


class AdminBarberOut(BarberOut):
    is_active: bool


class AdminServiceOut(ServiceOut):
    is_active: bool


class BookingOut(BaseModel):
    id: uuid.UUID
    status: str
    barber_id: uuid.UUID
    barber_name: str
    service_id: uuid.UUID
    service_name: str
    duration_minutes: int
    price_cents: Optional[int] = None
    starts_at: str
    ends_at: str
    starts_at_local: str
    ends_at_local: str
    customer_name: str
    customer_phone: str
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None
    cancellation_reason: Optional[str] = None
    cancelled_at: Optional[str] = None
    created_at: str


def booking_out(row, tz) -> BookingOut:
    """Build a BookingOut from a joined bookings/barbers/services row."""
    return BookingOut(
        id=row["id"],
        status=row["status"],
        barber_id=row["barber_id"],
        barber_name=row["barber_name"],
        service_id=row["service_id"],
        service_name=row["service_name"],
        duration_minutes=int((row["ends_at"] - row["starts_at"]).total_seconds() / 60),
        price_cents=row["price_cents"],
        starts_at=utc_iso(row["starts_at"]),
        ends_at=utc_iso(row["ends_at"]),
        starts_at_local=utc_to_wall(row["starts_at"], tz),
        ends_at_local=utc_to_wall(row["ends_at"], tz),
        customer_name=row["customer_name"],
        customer_phone=row["customer_phone"],
        notes=row["notes"],
        idempotency_key=row["idempotency_key"],
        cancellation_reason=row["cancellation_reason"],
        cancelled_at=utc_iso_opt(row["cancelled_at"]),
        created_at=utc_iso(row["created_at"]),
    )


class SlotOut(BaseModel):
    starts_at: str
    starts_at_local: str


class AvailabilityOut(BaseModel):
    barber_id: uuid.UUID
    barber_name: str
    service_id: uuid.UUID
    service_name: str
    date: str
    duration_minutes: int
    closed: bool
    available: list[SlotOut]


class ScheduleBookingOut(BaseModel):
    """Public calendar entry — contains no customer PII."""

    starts_at: str
    ends_at: str
    starts_at_local: str
    ends_at_local: str
    service_name: str
    status: str


class ScheduleOut(BaseModel):
    barber_id: uuid.UUID
    barber_name: str
    date: str
    closed: bool
    bookings: list[ScheduleBookingOut]


class AdminBookingsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    barber_id: Optional[uuid.UUID] = None
    include_cancelled: bool
    count: int
    bookings: list[BookingOut]


class HealthOut(BaseModel):
    status: str
    database: str
    version: str


class ServiceInfo(BaseModel):
    service: str
    version: str
    docs: str

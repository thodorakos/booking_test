"""Availability: the bookable-slot engine.

A slot is offered when ALL of these hold:
1. the shop is open that weekday (CLOSED_WEEKDAYS);
2. the service fits inside opening hours (wall-clock arithmetic);
3. the start aligns to the slot grid (SLOT_GRID_MINUTES);
4. it starts at least BOOKING_LEAD_MINUTES from now;
5. it does not overlap any *confirmed* booking of that barber.

Rule 5 as computed here is advisory (for rendering the picker). The
authoritative guarantee is Postgres itself: the EXCLUDE USING gist
constraint rejects an overlapping INSERT even when two customers submit the
same slot at the same instant — the loser gets a clean 409 SLOT_TAKEN.

Slot candidates are generated in LOCAL wall time (so the grid is :00/:30
as customers expect) and each is converted to UTC individually, which keeps
conversions correct across DST boundaries.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from config import Settings
from timeutils import WallClockError, naive_to_utc


def day_window(day: date, st: Settings) -> tuple[datetime, datetime] | None:
    """UTC (open, close) bounds for a day, or None when the shop is closed."""
    if day.weekday() in st.closed_weekdays:
        return None
    opened = naive_to_utc(datetime.combine(day, st.open_time), st.tz)
    closed = naive_to_utc(datetime.combine(day, st.close_time), st.tz)
    return opened, closed


def compute_slots(
    day: date,
    duration_minutes: int,
    busy: list[tuple[datetime, datetime]],
    now_utc: datetime,
    st: Settings,
) -> list[datetime]:
    """All bookable UTC start instants for a barber/day/service.

    ``busy`` holds the (start, end) UTC intervals of the barber's confirmed
    bookings around that day (queried with a safety buffer).
    """
    window = day_window(day, st)
    if window is None:
        return []

    open_wall = datetime.combine(day, st.open_time)
    close_wall = datetime.combine(day, st.close_time)
    earliest = now_utc + timedelta(minutes=st.lead_minutes)
    grid = timedelta(minutes=st.grid_minutes)
    duration = timedelta(minutes=duration_minutes)

    slots: list[datetime] = []
    cursor = open_wall + timedelta(minutes=(-open_wall.minute) % st.grid_minutes)
    while cursor + duration <= close_wall:
        try:
            start_utc = naive_to_utc(cursor, st.tz)
        except WallClockError:
            # Wall time inside a DST jump: it does not exist for customers
            # either — skip it and keep the grid aligned.
            cursor += grid
            continue
        end_utc = start_utc + duration
        if start_utc >= earliest and not any(s < end_utc and e > start_utc for s, e in busy):
            slots.append(start_utc)
        cursor += grid
    return slots

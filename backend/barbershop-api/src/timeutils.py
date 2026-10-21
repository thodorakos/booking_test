"""Timezone helpers for shop-local wall-clock times.

All instants are stored in Postgres as ``timestamptz`` (UTC). The API accepts
and returns *wall-clock* times in the shop's IANA zone (default
Europe/Athens). Two DST edge cases are detected explicitly and rejected with
a clear error instead of silently picking the wrong instant:

* nonexistent local times (clocks jump forward, spring);
* ambiguous local times (clocks fall back, the time occurs twice).

For Europe/Athens both transitions happen between 03:00 and 04:00 local on
Sundays, and this shop is closed Sundays, so in practice these never fire.
The checks exist so the system stays correct for any zone/hours you
configure later.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

WALL_FORMAT = "%Y-%m-%dT%H:%M"
ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_WALL_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class WallClockError(ValueError):
    """A wall-clock value is malformed, nonexistent, or ambiguous in the zone."""


def parse_wall_strict(value: str) -> datetime:
    """Parse ``YYYY-MM-DDTHH:MM`` into a naive datetime (no timezone yet)."""
    if not isinstance(value, str) or _WALL_RE.fullmatch(value) is None:
        raise WallClockError(
            f"expected 'YYYY-MM-DDTHH:MM' (e.g. 2026-10-25T14:00), got {value!r}"
        )
    try:
        return datetime.strptime(value, WALL_FORMAT)
    except ValueError as exc:
        raise WallClockError(f"not a valid date/time: {value!r} ({exc})") from None


def naive_to_utc(naive: datetime, tz: ZoneInfo) -> datetime:
    """Interpret a naive datetime as wall time in ``tz``; return aware UTC.

    Raises WallClockError for nonexistent/ambiguous wall times (DST edges).
    """
    early = naive.replace(tzinfo=tz, fold=0)
    late = naive.replace(tzinfo=tz, fold=1)
    if early.utcoffset() != late.utcoffset():
        # Either nonexistent (spring forward) or ambiguous (fall back).
        roundtrip = early.astimezone(timezone.utc).astimezone(tz).replace(
            tzinfo=None, fold=0
        )
        if roundtrip != naive:
            raise WallClockError(
                f"local time {naive:%Y-%m-%d %H:%M} does not exist in {tz.key} "
                "(clocks jump forward that night); pick another time"
            )
        raise WallClockError(
            f"local time {naive:%Y-%m-%d %H:%M} is ambiguous in {tz.key} "
            "(clocks fall back that night); pick another time"
        )
    return early.astimezone(timezone.utc)


def parse_date_strict(value: str) -> date:
    """Parse ``YYYY-MM-DD`` strictly; raises ValueError otherwise."""
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise ValueError(f"date must be YYYY-MM-DD, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"not a valid calendar date: {value!r}") from None


def utc_to_wall(dt: datetime, tz: ZoneInfo) -> str:
    """UTC instant -> shop-local wall string, e.g. '2026-10-25T14:00'."""
    return dt.astimezone(tz).strftime(WALL_FORMAT)


def utc_iso(dt: datetime) -> str:
    """UTC instant -> 'YYYY-MM-DDTHH:MM:SSZ'."""
    return dt.astimezone(timezone.utc).strftime(ISO_UTC_FORMAT)


def utc_iso_opt(dt: datetime | None) -> str | None:
    return utc_iso(dt) if dt is not None else None


def local_today(tz: ZoneInfo) -> date:
    """Today's date in shop-local time."""
    return datetime.now(timezone.utc).astimezone(tz).date()

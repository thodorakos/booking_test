"""Runtime settings, read per request from the Workers environment.

Values come from ``vars`` in wrangler.jsonc (plain) and secrets /
``.dev.vars`` (ADMIN_API_KEY). Parsing failures raise ApiError(500,
CONFIG_ERROR) so a misconfiguration is loud, never silent.

Defaults encode the agreed shop policy:
Mon-Sat 09:00-19:00 Europe/Athens, 30-minute slot grid, 1h booking lead
time, 60-day horizon, 24h free-cancellation cutoff, closed Sundays.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from errors import ApiError

DEFAULTS = {
    "SHOP_TIMEZONE": "Europe/Athens",
    "SHOP_OPEN": "09:00",
    "SHOP_CLOSE": "19:00",
    "SLOT_GRID_MINUTES": "30",
    "BOOKING_LEAD_MINUTES": "60",
    "BOOKING_HORIZON_DAYS": "60",
    "CANCEL_CUTOFF_HOURS": "24",
    "CLOSED_WEEKDAYS": "6",  # 0=Mon ... 6=Sun
    "ALLOWED_ORIGINS": "http://localhost:4321,http://127.0.0.1:4321",
    "QUERY_TIMEOUT_SECONDS": "8",
}


class _OsEnviron:
    """Fallback environment when running outside the Workers runtime."""

    def __getattr__(self, key: str):
        return os.environ.get(key)


def env_from_scope(scope) -> object:
    """The Workers env object from the ASGI scope (or an os.environ shim)."""
    env = scope.get("env")
    return env if env is not None else _OsEnviron()


def _var(env, key: str) -> str | None:
    try:
        value = getattr(env, key)
    except AttributeError:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text(env, key: str) -> str:
    value = _var(env, key)
    return value if value is not None else DEFAULTS[key]


def _hhmm(env, key: str) -> time:
    raw = _text(env, key)
    try:
        parsed = time.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be HH:MM, got {raw!r}") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError(f"{key} must be whole minutes (HH:MM)")
    return parsed


def _int(env, key: str, lo: int, hi: int) -> int:
    return _clamp_int(_text(env, key), key, lo, hi)


def _clamp_int(raw: str, key: str, lo: int, hi: int) -> int:
    try:
        parsed = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if not lo <= parsed <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}, got {parsed}")
    return parsed


@dataclass(frozen=True)
class Settings:
    tz: ZoneInfo
    tz_name: str
    open_time: time
    close_time: time
    grid_minutes: int
    lead_minutes: int
    horizon_days: int
    cancel_cutoff_hours: int
    closed_weekdays: frozenset[int]
    admin_api_key: str | None
    allowed_origins: tuple[str, ...]
    query_timeout: float


def settings_from_env(env) -> Settings:
    try:
        tz_name = _text(env, "SHOP_TIMEZONE")
        tz = ZoneInfo(tz_name)

        open_time = _hhmm(env, "SHOP_OPEN")
        close_time = _hhmm(env, "SHOP_CLOSE")
        if open_time >= close_time:
            raise ValueError("SHOP_OPEN must be earlier than SHOP_CLOSE")

        grid = _int(env, "SLOT_GRID_MINUTES", 1, 60)
        if 60 % grid != 0:
            raise ValueError(
                "SLOT_GRID_MINUTES must divide 60 evenly (5, 10, 15, 20, 30 or 60)"
            )

        closed_raw = _text(env, "CLOSED_WEEKDAYS")
        closed_weekdays = frozenset(
            _clamp_int(part, "CLOSED_WEEKDAYS", 0, 6)
            for part in closed_raw.split(",")
            if part.strip()
        )

        timeout_raw = _text(env, "QUERY_TIMEOUT_SECONDS")
        query_timeout = float(timeout_raw)
        if not 1.0 <= query_timeout <= 30.0:
            raise ValueError("QUERY_TIMEOUT_SECONDS must be between 1 and 30")

        return Settings(
            tz=tz,
            tz_name=tz_name,
            open_time=open_time,
            close_time=close_time,
            grid_minutes=grid,
            lead_minutes=_int(env, "BOOKING_LEAD_MINUTES", 0, 10080),
            horizon_days=_int(env, "BOOKING_HORIZON_DAYS", 1, 365),
            cancel_cutoff_hours=_int(env, "CANCEL_CUTOFF_HOURS", 0, 720),
            closed_weekdays=closed_weekdays,
            admin_api_key=_var(env, "ADMIN_API_KEY"),
            allowed_origins=tuple(
                o.strip() for o in _text(env, "ALLOWED_ORIGINS").split(",") if o.strip()
            ),
            query_timeout=query_timeout,
        )
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(500, "CONFIG_ERROR", f"Invalid environment configuration: {exc}") from exc


def settings_for(request) -> Settings:
    """Settings for the current request (env comes from the Workers scope)."""
    return settings_from_env(env_from_scope(request.scope))

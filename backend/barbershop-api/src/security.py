"""Access control helpers: the shop admin key and booking-phone matching.

There is deliberately no user auth framework — customers identify with the
phone number they booked with; the shop authenticates with a single shared
secret (X-Admin-Key) sent by the existing frontend's staff view or by
back-office tooling.
"""

from __future__ import annotations

import hmac

from fastapi import Request

from api_models import normalize_phone
from config import Settings, settings_for
from errors import ApiError


def admin_key_valid(request: Request, st: Settings) -> bool:
    """True when a valid X-Admin-Key was presented.

    No header -> False (caller falls back to the customer path).
    Wrong header -> raises 401. Header with no secret configured -> 503.
    """
    provided = request.headers.get("x-admin-key")
    if provided is None:
        return False
    expected = st.admin_api_key
    if not expected:
        raise ApiError(
            503,
            "ADMIN_DISABLED",
            "Admin access is disabled: set the ADMIN_API_KEY secret to enable it.",
        )
    if not hmac.compare_digest(provided, expected):
        raise ApiError(401, "FORBIDDEN", "Invalid admin key.")
    return True


def require_admin(request: Request) -> None:
    """FastAPI dependency for admin-only routers."""
    st = settings_for(request)
    if not admin_key_valid(request, st):
        raise ApiError(401, "FORBIDDEN", "Provide the shop admin key in the X-Admin-Key header.")


def phone_matches(candidate: str, stored: str) -> bool:
    """Constant-time comparison of a candidate phone against the stored one."""
    try:
        normalized = normalize_phone(candidate)
    except ValueError:
        return False
    return hmac.compare_digest(normalized, stored)

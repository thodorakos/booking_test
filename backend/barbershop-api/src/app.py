"""FastAPI application, shared by the Worker and local regression checks."""

from fastapi import FastAPI

import admin
import bookings
import catalog
from errors import install_error_handlers
from middleware import BodyLimitMiddleware, CorsMiddleware, RateLimitMiddleware

app = FastAPI(
    title="Barbershop Booking API",
    version="1.0.0",
    description=(
        "Barbershop backend: admin catalog management, availability, "
        "bookings and cancellations. No-double-booking is enforced by a Postgres "
        "exclusion constraint; retries are protected by idempotency keys. "
        "Interactive docs: GET /docs."
    ),
)

app.add_middleware(BodyLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.include_router(catalog.router)
app.include_router(bookings.router)
app.include_router(admin.router)
install_error_handlers(app)
# Wrap the entire app so even unhandled errors carry CORS and security headers.
app = CorsMiddleware(app)

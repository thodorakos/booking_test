"""FastAPI application, shared by the Worker and local regression checks."""

from fastapi import FastAPI

import admin
import bookings
import catalog
from errors import install_error_handlers
from middleware import BodyLimitMiddleware, CorsMiddleware

app = FastAPI(
    title="Barbershop Booking API",
    version="1.0.0",
    description=(
        "Booking backend for a 4-barber shop: barbers, services, availability, "
        "bookings and cancellations. No-double-booking is enforced by a Postgres "
        "exclusion constraint; retries are protected by idempotency keys. "
        "Interactive docs: GET /docs."
    ),
)

# The last middleware added is outermost, so CORS also covers body-limit errors.
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(CorsMiddleware)
app.include_router(catalog.router)
app.include_router(bookings.router)
app.include_router(admin.router)
install_error_handlers(app)

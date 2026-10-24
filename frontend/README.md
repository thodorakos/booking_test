# Alder frontend

Astro + React frontend for `../backend/barbershop-api`. The catalog, availability,
shop time zone, opening hours and cancellation policy come from the API at runtime.
No database connection or API service is needed during the static build.

## Local setup

```sh
npm ci
cp .env.example .env
npm run dev -- --host 0.0.0.0
```

Start the backend separately on port 8787 as described in its README.
`PUBLIC_API_URL` must be reachable from the visitor’s browser. For another device,
use the backend host’s address instead of localhost. In production set it to the
HTTPS Worker URL **before building**. Configure backend `ALLOWED_ORIGINS` for the
frontend’s exact origin (including the dev port). Do not serve HTTPS pages with
an HTTP API origin.

- `/book`: live services/barbers, dates in shop time, real booking creation.
  The same idempotency key and payload are reused on an uncertain retry; the form
  stays locked until that request’s outcome is known. Avoid closing or reloading
  the tab while confirmation is uncertain: pending retries live only in memory.
- `/manage`: lookup and cancel by booking reference and the customer’s phone,
  sent in JSON bodies so the phone stays out of request URLs.
- `/admin`: sign in using the existing backend `ADMIN_API_KEY` (never a public env
  variable), view/filter/cancel appointments and add/edit/deactivate/reactivate
  barbers and services. Admin cancellations bypass the customer cutoff. The key
  is held in tab memory only and is cleared on sign-out/reload. Every admin API
  request is authenticated by the backend; the page itself is static/public.
  Appointments open on today in the shop timezone. Quick ranges cover Today,
  3 days, 5 days, 1 week or 2 weeks, including today; custom ranges have no
  31-day limit.

The existing shop branding/contact details are presentation content; configure
those for your real shop before going live. Prices use the backend’s EUR cents;
a missing price displays “Ask in shop”. Historical bookings use their saved price
and duration. No SMS or payment integration is implied.

The shared API helper throttles requests per tab: 90 public reads, 8 customer
booking operations and 60 admin requests per minute. It honors the backend's
`Retry-After` cooldown, including non-JSON 429 responses, without automatic retries.
Reloading can reset frontend limits; the backend enforces IP limits independently.

Astro generates a script-hash Content Security Policy for built pages, restricted
to the configured API origin, local fonts and the existing image hosts. Inline
style attributes remain allowed for the current UI; inline executable scripts
are not allowed. Set `PUBLIC_API_URL` before building so CSP and API requests agree.
`public/_headers` adds framing, MIME, referrer, browser-permission and HTTPS headers
on Cloudflare Pages. Other static hosts must apply equivalent headers; Astro's
dev/preview server does not apply Pages header rules. CSP is active in build/preview,
not Astro dev mode. Existing input validation, React escaping, in-memory admin keys
and booking idempotency remain in use.

## Checks

```sh
npm run check
npm run lint
npm test
npm run build
```

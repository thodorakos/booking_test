const API_URL = (import.meta.env?.PUBLIC_API_URL || 'http://localhost:8787').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter = 0) { super(message); }
}

// shortcut: throttling is per tab; the backend enforces limits against direct requests.
const limits = {
  public: { max: 90, requests: [] as number[], until: 0 },
  bookings: { max: 8, requests: [] as number[], until: 0 },
  admin: { max: 60, requests: [] as number[], until: 0 },
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  init.signal?.throwIfAborted();
  const pathname = path.split('?')[0].replace(/\/+$/, '');
  const bucket = pathname === '/bookings' || pathname.startsWith('/bookings/') ? limits.bookings
    : pathname === '/admin' || pathname.startsWith('/admin/') ? limits.admin : limits.public;
  const now = Date.now();
  bucket.requests = bucket.requests.filter((time) => time > now - 60000);
  const waitUntil = Math.max(bucket.until, bucket.requests.length >= bucket.max ? bucket.requests[0] + 60000 : 0);
  if (waitUntil > now) {
    const seconds = Math.ceil((waitUntil - now) / 1000);
    throw new ApiError(429, 'RATE_LIMITED', `Too many requests. Please wait ${seconds} seconds before retrying.`, seconds);
  }
  bucket.requests.push(now);
  const headers = new Headers(init.headers);
  if (init.body) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init, headers, credentials: 'omit', cache: 'no-store',
      referrerPolicy: 'no-referrer',
      signal: AbortSignal.any([...(init.signal ? [init.signal] : []), AbortSignal.timeout(15000)]),
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach the booking service. Please retry.');
  }
  if (response.status === 429) {
    const retry = response.headers.get('Retry-After') || '';
    const seconds = /^\d+$/.test(retry) ? Number(retry) : (Date.parse(retry) - Date.now()) / 1000;
    const retryAfter = Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : 60;
    bucket.until = Math.max(bucket.until, Date.now() + retryAfter * 1000);
    throw new ApiError(429, 'RATE_LIMITED', `Too many requests. Please wait ${retryAfter} seconds before retrying.`, retryAfter);
  }
  let data;
  try { data = await response.json(); }
  catch { throw new ApiError(response.status, 'INVALID_RESPONSE', 'The booking service returned an unreadable response. Please retry.'); }
  if (!response.ok) {
    const error = data.error;
    const fields = error?.fields?.map((field: { field: string; message: string }) => `${field.field.replace(/^body\./, '')}: ${field.message}`).join(' ');
    throw new ApiError(response.status, error?.code || 'REQUEST_FAILED', fields || error?.message || 'Request failed. Please retry.');
  }
  return data as T;
}
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please retry.';
}

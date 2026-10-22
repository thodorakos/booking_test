const API_URL = (import.meta.env?.PUBLIC_API_URL || 'http://localhost:8787').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init, headers, credentials: 'omit', cache: 'no-store',
      signal: AbortSignal.any([...(init.signal ? [init.signal] : []), AbortSignal.timeout(15000)]),
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach the booking service. Please retry.');
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

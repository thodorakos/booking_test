import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const { URL, Response, AbortSignal } = globalThis;

let moduleVersion = 0;
async function load(file) {
  const source = await readFile(new URL(`../src/data/${file}.ts`, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return import(`data:text/javascript,${encodeURIComponent(outputText)}#${moduleVersion++}`);
}
const { formatPrice } = await load('catalog');
const { shopDate, addDays, formatWall, mergeSlots } = await load('availability');
const { api, ApiError } = await load('api');

test('EUR cents preserve zero, decimals and an unspecified price', () => {
  assert.equal(formatPrice(1500), '€15.00');
  assert.equal(formatPrice(0), '€0.00');
  assert.equal(formatPrice(1234), '€12.34');
  assert.equal(formatPrice(null), 'Ask in shop');
});
test('dates follow the shop timezone across midnight and DST', () => {
  assert.equal(shopDate('Europe/Athens', new Date('2026-10-24T22:30:00Z')), '2026-10-25');
  assert.equal(shopDate('America/New_York', new Date('2026-10-24T22:30:00Z')), '2026-10-24');
  assert.equal(addDays('2026-10-24', 2), '2026-10-26');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.match(formatWall('2026-10-25T10:30'), /10:30$/);
});
test('first available merges slots without losing the actual barber', () => {
  const slot = (time) => ({ starts_at: `2026-10-24T${time}:00Z`, starts_at_local: `2026-10-24T${time}` });
  const merged = mergeSlots([
    { barber_id: 'a', barber_name: 'Anna', available: [slot('11:00'), slot('10:00')] },
    { barber_id: 'b', barber_name: 'Bob', available: [slot('10:00'), slot('09:00')] },
  ]);
  assert.deepEqual(merged.map((entry) => [entry.starts_at_local.slice(11), entry.barber_id]), [['09:00', 'b'], ['10:00', 'a'], ['11:00', 'a']]);
  assert.deepEqual(mergeSlots([]), []);
});
test('API sends JSON, idempotency and admin headers without cookies or caching', async () => {
  const original = globalThis.fetch;
  const payload = JSON.stringify({ customer_name: 'Test' });
  try {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, 'http://localhost:8787/bookings');
      assert.equal(init.credentials, 'omit');
      assert.equal(init.cache, 'no-store');
      assert.equal(init.referrerPolicy, 'no-referrer');
      assert.equal(init.headers.get('Content-Type'), 'application/json');
      assert.equal(init.headers.get('Idempotency-Key'), 'retry-key');
      assert.equal(init.headers.get('X-Admin-Key'), 'test-key');
      assert.equal(init.body, payload);
      return new Response(JSON.stringify({ id: 'saved' }), { status: 201 });
    };
    assert.deepEqual(await api('/bookings', { method: 'POST', body: payload, headers: { 'Idempotency-Key': 'retry-key', 'X-Admin-Key': 'test-key' } }), { id: 'saved' });
  } finally { globalThis.fetch = original; }
});
test('API preserves machine-readable conflicts and validation details', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: 'SLOT_TAKEN', message: 'Choose another time.' } }), { status: 409 });
    await assert.rejects(api('/bookings'), (error) => error instanceof ApiError && error.status === 409 && error.code === 'SLOT_TAKEN');
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: 'VALIDATION_ERROR', fields: [{ field: 'body.customer_phone', message: 'Invalid phone' }] } }), { status: 422 });
    await assert.rejects(api('/bookings'), /customer_phone: Invalid phone/);
    globalThis.fetch = async () => { throw new TypeError('Network failure'); };
    await assert.rejects(api('/bookings'), (error) => error.code === 'NETWORK_ERROR' && error.status === 0);
    globalThis.fetch = async () => new Response('<html>Error</html>', { status: 502 });
    await assert.rejects(api('/bookings'), (error) => error.code === 'INVALID_RESPONSE' && error.status === 502);
  } finally { globalThis.fetch = original; }
});

test('API throttles concurrent booking requests across IDs and resets after a minute', async (t) => {
  const { api } = await load('api');
  let now = 100000;
  t.mock.method(Date, 'now', () => now);
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('{}'));
  await Promise.all(Array.from({ length: 8 }, (_, i) => api(`/bookings/id-${i}?phone=${i}`)));
  await assert.rejects(api('/bookings/another/cancel', { method: 'POST', body: '{}' }), (error) => error.status === 429 && error.retryAfter === 60);
  assert.equal(fetch.mock.callCount(), 8);
  await api('/shop');
  now += 60000;
  await api('/bookings/another');
  assert.equal(fetch.mock.callCount(), 10);
});

test('API honors numeric and dated Retry-After even for HTML rate-limit errors', async (t) => {
  let now = Date.parse('2026-10-24T12:00:00Z');
  t.mock.method(Date, 'now', () => now);
  for (const [header, expected] of [['5', 5], [new Date(now + 7000).toUTCString(), 7], ['invalid', 60], [null, 60]]) {
    now = Date.parse('2026-10-24T12:00:00Z');
    const { api } = await load('api');
    const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('<html>Limited</html>', {
      status: 429, headers: header ? { 'Retry-After': header } : {},
    }));
    await assert.rejects(api('/admin/barbers'), (error) => error.code === 'RATE_LIMITED' && error.retryAfter === expected);
    await assert.rejects(api('/admin/services'), (error) => error.retryAfter === expected);
    assert.equal(fetch.mock.callCount(), 1);
    fetch.mock.mockImplementation(async () => new Response('{}'));
    await api('/shop');
    now += expected * 1000;
    await api('/admin/barbers');
    fetch.mock.restore();
  }
});

test('API has separate public and admin budgets and does not charge pre-aborted requests', async (t) => {
  const { api } = await load('api');
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('{}'));
  const signal = AbortSignal.abort();
  for (let i = 0; i < 10; i++) await assert.rejects(api('/bookings', { signal }), { name: 'AbortError' });
  for (let i = 0; i < 90; i++) await api(`/availability?date=${i}`);
  await assert.rejects(api('/services'), (error) => error.status === 429);
  for (let i = 0; i < 60; i++) await api('/admin/services');
  await assert.rejects(api('/admin/bookings'), (error) => error.status === 429);
  await api('/bookings/reference');
  assert.equal(fetch.mock.callCount(), 151);
});

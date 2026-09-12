require('./register.cjs');
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
process.env.EXPO_PUBLIC_API_TOKEN = 'synthetic-test-token';
process.env.EXPO_PUBLIC_API_URL = 'http://test.local';
const { ApiError, quickAdd, listTransactions } = require('../src/api.ts');
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });

test('field error codes remain available without exposing server input text', async () => {
  global.fetch = async () => new Response(JSON.stringify({ error: { code: 'validation_error', field_errors: [
    { field: 'amount', code: 'too_many_decimals', message: 'sensitive echoed text' }, null,
  ] } }), { status: 422 });
  await assert.rejects(quickAdd({ amount: '1.001' }), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.fieldCode('amount'), 'too_many_decimals');
    assert.equal(error.message, 'http_422');
    return true;
  });
});
test('history pagination combines category and month filters and returns the cursor', async () => {
  global.fetch = async (url, options) => {
    const parsed = new URL(url);
    assert.equal(parsed.searchParams.get('category_id'), 'category');
    assert.equal(parsed.searchParams.get('month'), '2026-01');
    assert.equal(parsed.searchParams.get('cursor'), 'opaque=cursor');
    assert.ok(options.signal instanceof AbortSignal);
    return new Response(JSON.stringify({ items: [], next_cursor: 'next' }));
  };
  assert.equal((await listTransactions({ month: '2026-01', category_id: 'category', cursor: 'opaque=cursor' })).next_cursor, 'next');
});
test('ambiguous network failure is surfaced without automatically retrying a write', async () => {
  let requests = 0;
  global.fetch = async () => { requests++; throw new Error('untrusted transport details'); };
  await assert.rejects(quickAdd({ amount: '1.01' }), (error) => error instanceof ApiError && error.status === 0);
  assert.equal(requests, 1);
});

test('a stalled response body times out and lets the form recover', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  global.fetch = async (_url, { signal }) => ({
    status: 200, ok: true,
    json: () => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }),
  });
  const pending = quickAdd({ amount: '1.01' });
  await Promise.resolve();
  t.mock.timers.tick(20000);
  await assert.rejects(pending, (error) => error instanceof ApiError && error.status === 0);
});

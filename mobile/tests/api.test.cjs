require('./register.cjs');
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { ApiError, createApiClient } = require('../src/api.ts');
let credentials;
const transport = { getConnection: () => credentials, invalidate: (expected) => { if (credentials === expected) credentials = null; } };
const { quickAdd, listTransactions, categorizeTransaction } = createApiClient(transport);
const originalFetch = global.fetch;
beforeEach(() => { credentials = { baseUrl: 'https://test.example', token: 'synthetic-test-token' }; });
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
    assert.equal(options.headers.Authorization, 'Bearer synthetic-test-token');
    assert.equal(options.redirect, 'error');
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

test('category learning uses the existing authenticated transaction-centric endpoint', async () => {
  const input = { category_id: 'category-id', promote_to_rule: true,
    match_type: 'merchant_exact', apply_to_existing: false };
  global.fetch = async (url, options) => {
    assert.equal(url, 'https://test.example/api/v1/transactions/saved-id/categorize');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, 'Bearer synthetic-test-token');
    assert.deepEqual(JSON.parse(options.body), input);
    return new Response(JSON.stringify({ applied_to_existing_count: 0 }));
  };
  assert.equal((await categorizeTransaction('saved-id', input)).applied_to_existing_count, 0);
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

test('missing runtime credentials block requests even when a legacy public token is present', async () => {
  credentials = null;
  process.env.EXPO_PUBLIC_API_TOKEN = 'legacy-token-must-be-ignored';
  let calls = 0;
  global.fetch = async () => { calls++; throw new Error('must not fetch'); };
  await assert.rejects(listTransactions(), (e) => e.status === 401);
  assert.equal(calls, 0);
  delete process.env.EXPO_PUBLIC_API_TOKEN;
});

test('unauthorized responses invalidate only the active runtime credential', async () => {
  global.fetch = async () => new Response(JSON.stringify({ error: { code: 'unauthorized' } }), { status: 401 });
  await assert.rejects(listTransactions(), (e) => e.status === 401);
  assert.equal(credentials, null);
});

test('late unauthorized responses cannot invalidate a replacement session', async () => {
  let resolve;
  global.fetch = () => new Promise((r) => { resolve = r; });
  const pending = listTransactions();
  credentials = { baseUrl: 'https://test.example', token: 'replacement-token' };
  resolve(new Response('{}', { status: 401 }));
  await assert.rejects(pending, (e) => e.message === 'session_changed');
  assert.equal(credentials.token, 'replacement-token');
});

test('a response body from an old connection cannot populate a new session', async () => {
  let resolve;
  global.fetch = async () => ({ status: 200, ok: true, json: () => new Promise((r) => { resolve = r; }) });
  const pending = listTransactions();
  await Promise.resolve();
  credentials = { baseUrl: 'https://test.example', token: 'replacement-token' };
  resolve({ items: [{ note: 'old private data' }] });
  await assert.rejects(pending, (e) => e.message === 'session_changed');
});

test('a save completing across session replacement remains ambiguous and is never retried', async () => {
  for (const phase of ['headers', 'body']) {
    let resolve;
    let calls = 0;
    global.fetch = phase === 'headers'
      ? () => { calls++; return new Promise((r) => { resolve = r; }); }
      : async () => { calls++; return { status: 201, ok: true, json: () => new Promise((r) => { resolve = r; }) }; };
    const pending = quickAdd({ amount: '43.21' });
    await Promise.resolve();
    credentials = { baseUrl: 'https://test.example', token: `replacement-${phase}` };
    resolve(phase === 'headers' ? new Response('{}', { status: 201 }) : { transaction: { amount_minor: -4321 } });
    await assert.rejects(pending, (e) => e.message === 'session_changed' && e.status === 0);
    assert.equal(calls, 1);
  }
});

require('./register.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createSessionStore, normalizeBaseUrl } = require('../src/sessionStore.ts');
const { createAuthClient } = require('../src/authClient.ts');
const TOKEN = 'a'.repeat(43);
const BASE = 'https://personal.example';
const flush = () => new Promise((resolve) => setImmediate(resolve));

function fixture(initial = null) {
  let saved = initial;
  const events = [];
  const storage = {
    read: async () => { events.push('read'); return saved; },
    write: async (value) => { events.push('write'); saved = value; },
    remove: async () => { events.push('remove'); saved = null; },
  };
  const auth = {
    login: async (baseUrl, username, password) => {
      events.push('login');
      if (password !== 'synthetic passphrase') throw new Error('unauthorized');
      return Object.freeze({ baseUrl, token: TOKEN });
    },
    restore: async (_, credentials) => { events.push('verify'); return credentials; },
    logout: async () => { events.push('revoke'); },
  };
  return { storage, auth, events, saved: () => saved, store: createSessionStore(BASE, storage, auth) };
}

test('password login verifies before persistence and never puts credentials in observable state', async () => {
  const f = fixture();
  await f.store.restore();
  await f.store.signIn('owner', 'synthetic passphrase');
  assert.equal(f.store.getSnapshot().status, 'connected');
  assert.equal(f.saved().token, TOKEN);
  assert.equal(JSON.stringify(f.store.getSnapshot()).includes(TOKEN), false);
  assert.equal(JSON.stringify(f.saved()).includes('passphrase'), false);
  assert.ok(f.events.indexOf('login') < f.events.indexOf('write'));
  assert.ok(Object.isFrozen(f.store.getConnection()));
});

test('wrong password and unavailable credential storage never activate the app', async () => {
  const f = fixture();
  await f.store.restore();
  await assert.rejects(f.store.signIn('owner', 'wrong password'));
  assert.equal(f.saved(), null);
  f.storage.write = async () => { throw new Error('secure storage unavailable'); };
  await assert.rejects(f.store.signIn('owner', 'synthetic passphrase'), (e) => e.code === 'storage_write');
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.events.at(-1), 'revoke');
});

test('native restoration validates against the server before exposing data, and shares concurrent restoration', async () => {
  const f = fixture({ baseUrl: BASE, token: TOKEN });
  let finish;
  f.auth.restore = (_, credentials) => new Promise((resolve) => { finish = () => resolve(credentials); });
  const pending = f.store.restore();
  const same = f.store.restore();
  await flush();
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.store.getSnapshot().status, 'loading');
  finish();
  await Promise.all([pending, same]);
  assert.equal(f.events.filter((event) => event === 'read').length, 1);
  assert.equal(f.store.getConnection().token, TOKEN);
});

test('expired server sessions, legacy codes and credentials for a different server are discarded', async () => {
  for (const saved of [{ baseUrl: BASE, token: 'legacy-code' }, { baseUrl: 'https://other.example', token: TOKEN }, {}, []]) {
    const f = fixture(saved);
    await f.store.restore();
    assert.equal(f.saved(), null);
    assert.equal(f.store.getConnection(), null);
  }
  const f = fixture({ baseUrl: BASE, token: TOKEN });
  f.auth.restore = async () => null;
  await f.store.restore();
  assert.equal(f.saved(), null);
  assert.equal(f.store.getSnapshot().status, 'disconnected');
});

test('a failed restoration remains private and can retry when the server wakes', async () => {
  const f = fixture({ baseUrl: BASE, token: TOKEN });
  f.auth.restore = async () => { throw new Error('network'); };
  await f.store.restore();
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.store.getSnapshot().error, 'storage_read');
  f.auth.restore = async (_, saved) => saved;
  await f.store.restore();
  assert.equal(f.store.getSnapshot().status, 'connected');
});

test('logout revokes before clearing storage; failed revocation is visible and retryable', async () => {
  const f = fixture();
  await f.store.restore();
  await f.store.signIn('owner', 'synthetic passphrase');
  f.auth.logout = async () => { throw new Error('offline'); };
  await f.store.disconnect();
  assert.equal(f.store.getSnapshot().error, 'logout');
  assert.equal(f.store.getSnapshot().status, 'connected');
  assert.equal(f.saved().token, TOKEN);
  f.auth.logout = async () => { f.events.push('revoke'); };
  await f.store.disconnect();
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.saved(), null);
  assert.deepEqual(f.events.slice(-2), ['revoke', 'remove']);
});

test('a late 401 cannot invalidate a newer session and expiry retains draft eligibility', async () => {
  const f = fixture();
  await f.store.restore();
  await f.store.signIn('owner', 'synthetic passphrase');
  const old = f.store.getConnection();
  f.store.invalidate(old);
  assert.equal(f.store.getSnapshot().status, 'expired');
  await flush();
  assert.equal(f.saved(), null);
  await f.store.signIn('owner', 'synthetic passphrase');
  f.store.invalidate(old);
  assert.equal(f.store.getSnapshot().status, 'connected');
  assert.equal(f.store.getSnapshot().version, 2);
});

test('pending login and pending credential cleanup serialize session changes', async () => {
  const f = fixture();
  await f.store.restore();
  let finish;
  f.auth.login = () => new Promise((resolve) => { finish = () => resolve({ baseUrl: BASE, token: TOKEN }); });
  const pending = f.store.signIn('owner', 'anything');
  await assert.rejects(f.store.signIn('owner', 'another'), (e) => e.code === 'busy');
  finish();
  await pending;
  f.storage.remove = () => new Promise((resolve) => { finish = resolve; });
  f.store.invalidate(f.store.getConnection());
  await assert.rejects(f.store.signIn('owner', 'another'), (e) => e.code === 'busy');
  finish();
  await flush();
  assert.equal(f.store.getSnapshot().busy, false);
});

test('web refresh restores a cookie session without reading or storing a secret in JavaScript', async (t) => {
  const original = global.fetch;
  t.after(() => { global.fetch = original; });
  global.fetch = async (url, options) => {
    assert.equal(url, `${BASE}/api/v1/auth/session`);
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers.Authorization, undefined);
    assert.equal(options.cache, 'no-store');
    return new Response(JSON.stringify({ authenticated: true, expires_at: '2026-12-01T00:00:00Z' }));
  };
  const f = fixture();
  const store = createSessionStore(BASE, f.storage, createAuthClient(true));
  await store.restore();
  assert.equal(store.getSnapshot().status, 'connected');
  assert.equal(store.getConnection().token, null);
  assert.equal(f.saved(), null);
});

test('browser login omits bearer secrets while native login requires a valid issued token', async (t) => {
  const original = global.fetch;
  t.after(() => { global.fetch = original; });
  global.fetch = async (_, options) => {
    assert.equal(options.headers['X-MoneySaver-Client'], 'web');
    assert.equal(JSON.parse(options.body).client, 'web');
    assert.equal(JSON.parse(options.body).password, ' password with spaces ');
    return new Response(JSON.stringify({ authenticated: true, expires_at: '2026-12-01T00:00:00Z' }));
  };
  assert.equal((await createAuthClient(true).login(BASE, 'owner', ' password with spaces ')).token, null);
  global.fetch = async () => new Response(JSON.stringify({ authenticated: true, expires_at: '2026-12-01T00:00:00Z', access_token: 'legacy-short-code' }));
  await assert.rejects(createAuthClient(false).login(BASE, 'owner', 'password'));
});

test('login errors and timeouts stay generic without retrying submitted passwords', async (t) => {
  const original = global.fetch;
  t.after(() => { global.fetch = original; });
  let calls = 0;
  global.fetch = async () => { calls++; return new Response('sensitive upstream detail', { status: 429 }); };
  await assert.rejects(createAuthClient(true).login(BASE, 'owner', 'secret'), (e) => e.status === 429 && !e.message.includes('detail'));
  assert.equal(calls, 1);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  global.fetch = async (_, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))));
  const pending = createAuthClient(true).restore(BASE, null);
  t.mock.timers.tick(90000);
  await assert.rejects(pending, (e) => e.status === 0);
});

test('credentials cannot be sent to public cleartext or credential-bearing URLs', () => {
  for (const url of ['http://public.example', 'https://user:password@example.com', 'https://example.com?token=secret', 'https://example.com/#secret', 'file:///tmp']) {
    assert.throws(() => normalizeBaseUrl(url), (e) => e.code === 'invalid_url');
  }
  for (const url of [BASE, 'http://localhost:8000', 'http://127.0.0.1:8000', 'http://192.168.1.7:8000']) {
    assert.equal(normalizeBaseUrl(`${url}/`), url);
  }
});

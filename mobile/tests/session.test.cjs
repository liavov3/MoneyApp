require('./register.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createSessionStore, ConnectionError, normalizeBaseUrl } = require('../src/sessionStore.ts');

function fixture(initial = null) {
  let saved = initial;
  const events = [];
  const storage = {
    read: async () => { events.push('read'); return saved; },
    write: async (value) => { events.push('write'); saved = value; },
    remove: async () => { events.push('remove'); saved = null; },
  };
  return { storage, events, saved: () => saved, store: createSessionStore('https://personal.example', storage) };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));

test('connection verifies before secure persistence and exposes no credential in UI state', async () => {
  const f = fixture();
  await f.store.restore();
  assert.equal(f.store.getConnection(), null);
  await f.store.connect(' synthetic-token ', async (credentials) => {
    assert.equal(credentials.token, 'synthetic-token');
    assert.equal(f.store.getConnection(), null);
    assert.equal(f.saved(), null);
    f.events.push('verify');
  });
  assert.deepEqual(f.events, ['read', 'verify', 'write']);
  assert.equal(f.store.getSnapshot().status, 'connected');
  assert.equal(JSON.stringify(f.store.getSnapshot()).includes('synthetic-token'), false);
  assert.equal(Object.isFrozen(f.store.getConnection()), true);
});

test('rejected credentials never persist or activate', async () => {
  const f = fixture();
  await f.store.restore();
  await assert.rejects(f.store.connect('wrong-code', async () => { throw new Error('unauthorized'); }));
  assert.equal(f.saved(), null);
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.store.getSnapshot().busy, false);
});

test('secure-storage write failure leaves app gated and supports retry', async () => {
  const f = fixture();
  await f.store.restore();
  let fails = true;
  const write = f.storage.write;
  f.storage.write = async (value) => { if (fails) throw new Error('native failure details'); await write(value); };
  await assert.rejects(f.store.connect('code', async () => {}), (e) => e instanceof ConnectionError && e.code === 'storage_write');
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.store.getSnapshot().status, 'disconnected');
  fails = false;
  await f.store.connect('code', async () => {});
  assert.equal(f.store.getSnapshot().status, 'connected');
});

test('restoration is shared and binds credentials to the exact configured server', async () => {
  const f = fixture({ baseUrl: 'https://personal.example/', token: 'saved-code' });
  await Promise.all([f.store.restore(), f.store.restore()]);
  assert.deepEqual(f.events, ['read']);
  assert.equal(f.store.getConnection().token, 'saved-code');
  const other = fixture({ baseUrl: 'https://different.example', token: 'other-server-code' });
  await other.store.restore();
  assert.equal(other.store.getConnection(), null);
  assert.equal(other.saved(), null);
});

test('failed restoration never exposes data and can read again after recovery', async () => {
  const f = fixture({ baseUrl: 'https://personal.example', token: 'saved-code' });
  const read = f.storage.read;
  f.storage.read = async () => { throw new Error('native details'); };
  await f.store.restore();
  assert.equal(f.store.getSnapshot().error, 'storage_read');
  assert.equal(f.store.getConnection(), null);
  f.storage.read = read;
  await f.store.restore();
  assert.equal(f.store.getSnapshot().status, 'connected');
});

test('expiration clears credentials while retaining form state eligibility; a stale 401 cannot expire a new connection', async () => {
  const f = fixture();
  await f.store.restore();
  await f.store.connect('old-code', async () => {});
  const old = f.store.getConnection();
  f.store.invalidate(old);
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.store.getSnapshot().status, 'expired');
  await flush();
  assert.equal(f.saved(), null);
  await f.store.connect('new-code', async () => {});
  f.store.invalidate(old);
  assert.equal(f.store.getConnection().token, 'new-code');
  assert.equal(f.store.getSnapshot().version, 2);
});

test('disconnect hides data immediately, surfaces erase failure, and retries removal', async () => {
  const f = fixture();
  await f.store.restore();
  await f.store.connect('saved-code', async () => {});
  const remove = f.storage.remove;
  f.storage.remove = async () => { throw new Error('native erase failed'); };
  const disconnecting = f.store.disconnect();
  assert.equal(f.store.getConnection(), null);
  assert.equal(f.store.getSnapshot().status, 'disconnected');
  await disconnecting;
  assert.equal(f.store.getSnapshot().error, 'storage_clear');
  f.storage.remove = remove;
  await f.store.disconnect();
  assert.equal(f.saved(), null);
  assert.equal(f.store.getSnapshot().error, null);
});

test('connection cannot overtake pending credential removal or another connection', async () => {
  const f = fixture();
  await f.store.restore();
  let verified;
  const first = f.store.connect('code', () => new Promise((resolve) => { verified = resolve; }));
  await assert.rejects(f.store.connect('second', async () => {}), (e) => e.code === 'busy');
  verified();
  await first;
  let removed;
  f.storage.remove = () => new Promise((resolve) => { removed = resolve; });
  f.store.invalidate(f.store.getConnection());
  await assert.rejects(f.store.connect('new-code', async () => {}), (e) => e.code === 'busy');
  removed();
  await flush();
  await f.store.connect('new-code', async () => {});
  assert.equal(f.store.getConnection().token, 'new-code');
});

test('malformed stored values and public cleartext destinations fail closed', async () => {
  for (const stored of [[], {}, { token: 'code', baseUrl: 'http://public.example' }, { token: '\n', baseUrl: 'https://personal.example' }]) {
    const f = fixture(stored);
    await f.store.restore();
    assert.equal(f.store.getConnection(), null);
  }
  for (const url of ['http://public.example', 'https://user:password@example.com', 'https://example.com?token=secret', 'https://example.com/#secret', 'file:///tmp']) {
    assert.throws(() => normalizeBaseUrl(url), (e) => e.code === 'invalid_url');
  }
  for (const url of ['https://example.com', 'http://localhost:8000', 'http://127.0.0.1:8000', 'http://192.168.1.7:8000', 'http://172.16.0.5:8000', 'http://10.0.0.5:8000']) {
    assert.equal(normalizeBaseUrl(`${url}/`), url);
  }
});

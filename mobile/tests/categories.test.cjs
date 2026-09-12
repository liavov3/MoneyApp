require('./register.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createCategoryStore } = require('../src/categoryStore.ts');

test('concurrent screens share one fetch and observe the recovered categories', async () => {
  let calls = 0;
  let resolve;
  const result = new Promise((r) => { resolve = r; });
  const store = createCategoryStore(() => { calls++; return result; });
  const first = [];
  const second = [];
  store.subscribe(() => first.push(store.getSnapshot()));
  store.subscribe(() => second.push(store.getSnapshot()));
  const pending = store.reload();
  assert.equal(store.reload(), pending);
  resolve([{ id: 'groceries' }]);
  await pending;
  assert.equal(calls, 1);
  assert.equal(first.length, 2);
  assert.deepEqual(first, second);
  assert.deepEqual(store.getSnapshot().items, [{ id: 'groceries' }]);
});
test('a failed first load can be explicitly retried without losing subscribers', async () => {
  let calls = 0;
  const store = createCategoryStore(async () => {
    if (++calls === 1) throw new Error('network');
    return [{ id: 'groceries' }];
  });
  await store.reload();
  assert.deepEqual(store.getSnapshot(), { items: null, error: true, loading: false });
  await store.reload();
  assert.equal(store.getSnapshot().error, false);
  assert.deepEqual(store.getSnapshot().items, [{ id: 'groceries' }]);
});
test('failed refresh keeps cached categories, and unmounted screens unsubscribe', async () => {
  let fail = false;
  const store = createCategoryStore(async () => {
    if (fail) throw new Error('network');
    return [{ id: 'groceries' }];
  });
  await store.reload();
  let notifications = 0;
  const unsubscribe = store.subscribe(() => notifications++);
  unsubscribe();
  fail = true;
  await store.reload();
  assert.deepEqual(store.getSnapshot().items, [{ id: 'groceries' }]);
  assert.equal(store.getSnapshot().error, true);
  assert.equal(notifications, 0);
});

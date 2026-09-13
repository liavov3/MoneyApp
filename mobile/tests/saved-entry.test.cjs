require('./register.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { savedEntryFrom, undoSavedEntry } = require('../src/savedEntry.ts');
const { ApiError } = require('../src/api.ts');

const transaction = { id: 'newly-saved-id', amount_minor: -3350, currency: 'ILS', transaction_type: 'expense' };

test('saved feedback preserves exact transaction values and handles both advisory warnings', () => {
  const entry = savedEntryFrom({ transaction, warnings: [
    { code: 'duplicate_looking', similar_transaction_id: 'previous-id', message: 'ignored external copy' },
    { code: 'large_amount', amount_minor: -1200000 },
  ] });
  assert.equal(entry.transaction, transaction);
  assert.equal(entry.transaction.amount_minor, -3350); // never take the displayed amount from a warning
  assert.equal(entry.duplicateLooking, true);
  assert.equal(entry.largeAmount, true);
});

test('ordinary saves and unrecognized warning data do not create fake warnings', () => {
  for (const warnings of [[], null, [null, { code: 'future_warning' }]]) {
    const entry = savedEntryFrom({ transaction, warnings });
    assert.equal(entry.duplicateLooking, false);
    assert.equal(entry.largeAmount, false);
  }
});

test('undo targets only the newly saved id, never the similar transaction', async () => {
  const entry = savedEntryFrom({ transaction, warnings: [{ code: 'duplicate_looking', similar_transaction_id: 'keep-this-original' }] });
  const removed = [];
  await undoSavedEntry(entry, async (id) => { removed.push(id); });
  assert.deepEqual(removed, ['newly-saved-id']);
});

test('an explicit undo retry accepts an already-absent row but never retries a failure automatically', async () => {
  const entry = savedEntryFrom({ transaction, warnings: [] });
  await undoSavedEntry(entry, async () => { throw new ApiError('not_found', 404); });
  for (const status of [0, 401, 500]) {
    let calls = 0;
    await assert.rejects(undoSavedEntry(entry, async () => { calls++; throw new ApiError('failed', status); }), (e) => e.status === status);
    assert.equal(calls, 1);
  }
});

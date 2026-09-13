require('./register.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { savedEntryFrom, undoSavedEntry, rememberSavedCategory } = require('../src/savedEntry.ts');
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

const categorized = { ...transaction, merchant_id: 'merchant-id', merchant_display_name: 'Golda',
  category_id: 'eating-id', category_key: 'eating_out' };
const offer = { offer: true, merchant_id: 'merchant-id', suggested_category_id: 'eating-id', suggested_category_key: 'eating_out' };
const learningEntry = () => savedEntryFrom({ transaction: categorized, warnings: [], rule_prompt: offer });
const confirmation = (categoryId = 'eating-id') => ({
  transaction: { ...categorized, category_id: categoryId },
  rule: { category_id: categoryId, match_type: 'merchant_exact', source: 'user_correction', is_active: true },
  applied_to_existing_count: 0,
});

test('rule offers must match the saved merchant and category exactly', () => {
  assert.deepEqual(learningEntry().rulePrompt, offer);
  for (const rule_prompt of [null, { offer: false }, { offer: true },
    { ...offer, merchant_id: 'different-merchant' },
    { ...offer, suggested_category_id: 'different-category' },
    { ...offer, suggested_category_key: 'other_spending' }]) {
    assert.equal(savedEntryFrom({ transaction: categorized, warnings: [], rule_prompt }).rulePrompt, null);
  }
});

test('explicit remember targets the saved row and opts out of rewriting history', async () => {
  const calls = [];
  const result = await rememberSavedCategory(learningEntry(), 'eating-id', async (...args) => {
    calls.push(args); return confirmation();
  });
  assert.deepEqual(calls, [['newly-saved-id', { category_id: 'eating-id', promote_to_rule: true,
    match_type: 'merchant_exact', apply_to_existing: false }]]);
  assert.equal(result.transaction.amount_minor, -3350);
});

test('the chosen replacement category is explicit and a failed remember is never automatically retried', async () => {
  let calls = 0;
  await rememberSavedCategory(learningEntry(), 'shopping-id', async (id, body) => {
    calls++; assert.equal(body.category_id, 'shopping-id'); return confirmation('shopping-id');
  });
  assert.equal(calls, 1);
  for (const status of [0, 401, 404, 500]) {
    calls = 0;
    await assert.rejects(rememberSavedCategory(learningEntry(), 'eating-id', async () => {
      calls++; throw new ApiError('failed', status);
    }), error => error.status === status);
    assert.equal(calls, 1);
  }
});

test('unconfirmed, mismatched, or historical rule changes are not reported as success', async () => {
  for (const result of [{ ...confirmation(), rule: null },
    { ...confirmation(), transaction: { ...categorized, merchant_id: 'unexpected' } },
    { ...confirmation(), applied_to_existing_count: 1 }]) {
    await assert.rejects(rememberSavedCategory(learningEntry(), 'eating-id', async () => result), error => error.status === 0);
  }
  await assert.rejects(rememberSavedCategory({ ...learningEntry(), rulePrompt: null }, 'eating-id',
    async () => { assert.fail('must not call the API without an offer'); }));
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

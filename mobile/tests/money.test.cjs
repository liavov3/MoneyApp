require('./register.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { shekelToMinor, minorToInput, nextDateForDay, addMonths } = require('../src/format.ts');
const { transactionPatch } = require('../src/transactionEdit.ts');

test('decimal entry retains exact agorot and accepts the decimal comma', () => {
  for (const [text, minor] of [['0.01', 1], ['33.50', 3350], ['33,50', 3350], ['9999999.99', 999999999]]) {
    assert.equal(shekelToMinor(text), minor);
    assert.equal(shekelToMinor(minorToInput(minor)), minor);
  }
});
test('invalid or unsafe amounts never become rounded money', () => {
  for (const text of ['', '0', '-1', '1.001', 'NaN', 'Infinity', '1e3', '900719925474099.99']) {
    assert.equal(shekelToMinor(text), null, text);
  }
});
test('month navigation and end-of-month commitments use calendar dates', () => {
  assert.equal(addMonths('2025-12', 1), '2026-01');
  assert.equal(addMonths('2026-01', -1), '2025-12');
  assert.equal(nextDateForDay(31, new Date(2024, 1, 29)), '2024-02-29');
  assert.equal(nextDateForDay(28, new Date(2024, 1, 29)), '2024-03-28');
  assert.equal(nextDateForDay(31, new Date(2026, 3, 30)), '2026-04-30');
});
const original = { transaction_type: 'refund', amount_minor: 3350, category_id: 'groceries', occurred_on: '2026-01-02', note: null };
const edit = { amount: '33.50', type: 'refund', categoryId: 'groceries', occurredOn: '2026-01-02', note: '' };
test('unchanged refund sends no patch, note edit preserves category and refund type', () => {
  assert.deepEqual(transactionPatch(original, edit), {});
  assert.deepEqual(transactionPatch(original, { ...edit, note: 'changed' }), { note: 'changed' });
});
test('unchanged negative adjustment keeps its sign; unsupported amount edits fail safely', () => {
  const adjustment = { ...original, transaction_type: 'adjustment', amount_minor: -3350 };
  assert.deepEqual(transactionPatch(adjustment, { ...edit, type: 'adjustment', note: 'changed' }), { note: 'changed' });
  assert.throws(() => transactionPatch(adjustment, { ...edit, type: 'adjustment', amount: '34' }), /signed_adjustment/);
});
test('intentional type, category, and exact amount edits are sent', () => {
  assert.deepEqual(transactionPatch(original, { ...edit, type: 'expense', categoryId: null, amount: '40,01' }), {
    amount: '40.01', transaction_type: 'expense', category_id: null,
  });
});

test('merchant edits affect only that field, with explicit clearing and no-op preservation', () => {
  const transaction = { ...original, merchant_display_name: 'Original Store', merchant_id: 'original' };
  assert.deepEqual(transactionPatch(transaction, { ...edit, merchant: 'Replacement' }), { merchant_input: 'Replacement' });
  assert.deepEqual(transactionPatch(transaction, { ...edit, merchant: '  ' }), { merchant_id: null });
  assert.deepEqual(transactionPatch(transaction, { ...edit, merchant: 'Original Store' }), {});
  assert.deepEqual(transactionPatch(transaction, { ...edit, note: 'changed' }), { note: 'changed' });
});

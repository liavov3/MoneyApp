import { minorToInput, shekelToMinor } from './format';
import type { PatchTransactionInput, TransactionOut } from './types';

export type EditType = 'expense' | 'income' | 'refund' | 'adjustment';

export function transactionPatch(
  original: TransactionOut,
  edited: { amount: string; type: EditType; categoryId: string | null; occurredOn: string; note: string },
): PatchTransactionInput {
  const minor = shekelToMinor(edited.amount);
  if (minor === null) throw new Error('invalid_amount');
  const patch: PatchTransactionInput = {};
  if (minor !== Math.abs(original.amount_minor)) {
    // The current API only accepts positive adjustment magnitudes. Never
    // reverse a negative adjustment while editing unrelated fields.
    if (original.amount_minor < 0 && edited.type === 'adjustment') throw new Error('signed_adjustment');
    patch.amount = minorToInput(minor);
  }
  if (edited.type !== original.transaction_type) patch.transaction_type = edited.type;
  if (edited.categoryId !== original.category_id) patch.category_id = edited.categoryId;
  if (edited.occurredOn !== original.occurred_on) patch.occurred_on = edited.occurredOn;
  const note = edited.note.trim() || null;
  if (note !== original.note) patch.note = note;
  return patch;
}

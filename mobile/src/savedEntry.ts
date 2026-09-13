import { ApiError } from './api';
import type { QuickAddResponse, TransactionOut } from './types';

export type SavedEntry = {
  transaction: TransactionOut;
  duplicateLooking: boolean;
  largeAmount: boolean;
};

export function savedEntryFrom(response: QuickAddResponse): SavedEntry {
  const warnings = Array.isArray(response.warnings) ? response.warnings : [];
  const has = (code: string) => warnings.some((warning) => warning !== null && typeof warning === 'object' && warning.code === code);
  return { transaction: response.transaction, duplicateLooking: has('duplicate_looking'), largeAmount: has('large_amount') };
}

export async function undoSavedEntry(entry: SavedEntry, remove: (id: string) => Promise<void>): Promise<void> {
  try {
    // Never act on similar_transaction_id: undo removes only this new save.
    await remove(entry.transaction.id);
  } catch (error) {
    // A prior explicit undo can succeed while its response is lost. On a
    // user-triggered retry, an already-absent row is the desired state.
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }
}

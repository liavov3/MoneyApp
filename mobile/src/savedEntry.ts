import { ApiError } from './api';
import type { CategorizeInput, CategorizeResponse, QuickAddResponse, RulePrompt, TransactionOut } from './types';

export type SavedEntry = {
  transaction: TransactionOut;
  duplicateLooking: boolean;
  largeAmount: boolean;
  rulePrompt: Extract<RulePrompt, { offer: true }> | null;
};

export function savedEntryFrom(response: QuickAddResponse): SavedEntry {
  const warnings = Array.isArray(response.warnings) ? response.warnings : [];
  const has = (code: string) => warnings.some((warning) => warning !== null && typeof warning === 'object' && warning.code === code);
  const prompt = response.rule_prompt;
  const txn = response.transaction;
  // Only offer the mapping actually saved; reject mismatched/partial metadata.
  const rulePrompt = prompt?.offer === true && !!txn.merchant_display_name?.trim()
    && typeof prompt.merchant_id === 'string' && prompt.merchant_id === txn.merchant_id
    && typeof prompt.suggested_category_id === 'string' && prompt.suggested_category_id === txn.category_id
    && typeof prompt.suggested_category_key === 'string' && prompt.suggested_category_key === txn.category_key
    ? prompt : null;
  return { transaction: txn, duplicateLooking: has('duplicate_looking'), largeAmount: has('large_amount'), rulePrompt };
}

export async function rememberSavedCategory(entry: SavedEntry, categoryId: string,
  categorize: (id: string, body: CategorizeInput) => Promise<CategorizeResponse>): Promise<CategorizeResponse> {
  if (!entry.rulePrompt || !categoryId) throw new Error('missing_rule_offer');
  const result = await categorize(entry.transaction.id, {
    category_id: categoryId, promote_to_rule: true,
    match_type: 'merchant_exact', apply_to_existing: false,
  });
  if (result.transaction.id !== entry.transaction.id || result.transaction.merchant_id !== entry.rulePrompt.merchant_id
      || result.transaction.category_id !== categoryId || result.rule?.category_id !== categoryId
      || result.rule.match_type !== 'merchant_exact' || result.rule.source !== 'user_correction'
      || !result.rule.is_active || result.applied_to_existing_count !== 0) {
    throw new ApiError('rule_confirmation_unavailable', 0);
  }
  return result;
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

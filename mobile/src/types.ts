// Mirrors the frozen GET /api/v1/home response (API_CONTRACT §13) and the
// GET /api/v1/categories item (§6). No invented fields.

export interface CategoryTotal {
  category_id: string;
  category_key: string | null;
  label_en: string;
  total_minor: number;
}

export interface RecentTxn {
  id: string;
  amount_minor: number;
  currency: string;
  merchant_display_name: string | null;
  category_key: string | null;
  occurred_on: string;
  is_uncategorized: boolean;
}

export interface UpcomingCommitment {
  template_id: string;
  name_present: boolean;
  category_key: string | null;
  amount_minor: number;
  next_expected_date: string;
}

export interface KnownThisMonth {
  spent_actual_minor: number;
  committed_projected_minor: number;
}

export interface HomeResponse {
  month: string;
  currency: string;
  spent_so_far_minor: number;
  top_category: CategoryTotal | null;
  category_totals: CategoryTotal[];
  recent_transactions: RecentTxn[];
  uncategorized_count: number;
  upcoming_commitments: UpcomingCommitment[];
  committed_amount_minor: number;
  known_this_month: KnownThisMonth;
  warnings: Array<Record<string, unknown>>;
}

export interface CategoryOut {
  id: string;
  key: string | null;
  label_en: string;
  label_he: string | null;
  layer: string;
  included_in_actual_spending: boolean;
  included_in_cash_flow: boolean;
  is_system: boolean;
}

// Full transaction shape (quick-add response / list / read) — API_CONTRACT §8/§9.
export interface TransactionOut {
  id: string;
  amount_minor: number;
  currency: string;
  transaction_type: string;
  source: string;
  merchant_id: string | null;
  merchant_display_name: string | null;
  category_id: string | null;
  category_key: string | null;
  occurred_on: string;
  note: string | null;
  is_card_settlement: boolean;
  created_at: string;
  updated_at: string;
}

export interface QuickAddResponse {
  transaction: TransactionOut;
  warnings: Array<Record<string, unknown>>;
  category_suggestion: {
    category_id: string;
    category_key: string | null;
    source: string;
  } | null;
  rule_prompt: Record<string, unknown>;
  alias_suggestion: Record<string, unknown> | null;
}

export interface TransactionListResponse {
  items: TransactionOut[];
  next_cursor: string | null;
}

export interface RecentMerchant {
  merchant_id: string;
  display_name: string;
  suggested_category_id: string | null;
  suggested_category_key: string | null;
  suggested_category_source: string | null;
  last_used_at: string;
}

export interface MerchantSuggestion {
  merchant_id: string;
  display_name: string;
  confidence: string;
  requires_confirmation: boolean;
  matched_via: string;
  suggested_category_id: string | null;
  suggested_category_key: string | null;
  suggested_category_source: string;
}

export interface MerchantSuggestionsResponse {
  query_confidence: string;
  auto_select_merchant_id: string | null;
  items: MerchantSuggestion[];
}

// What Quick Add sends (amount required; everything else optional). §8/§14.
export interface QuickAddInput {
  amount: string;
  transaction_type?: string;
  occurred_on?: string;
  note?: string;
  category_id?: string;
  merchant_input?: string;
}

// PATCH /transactions/{id} — partial edit (§9). Only provided keys are applied;
// `category_id: null` clears the category. Merchant is NOT editable (server
// drops merchant fields), so it is intentionally absent here.
export interface PatchTransactionInput {
  amount?: string;
  transaction_type?: string;
  occurred_on?: string;
  note?: string | null;
  category_id?: string | null;
}

// Recurring expense template (API_CONTRACT §12). Amount stored signed-negative;
// the API accepts/returns a non-negative magnitude convention on input.
export interface TemplateOut {
  id: string;
  name: string;
  amount_minor: number;
  currency: string;
  category_id: string;
  category_key: string | null;
  merchant_id: string | null;
  cadence: string;
  next_expected_date: string;
  counts_in_projection: boolean;
  is_active: boolean;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecurringListResponse {
  items: TemplateOut[];
}

export type GoalType = 'expense' | 'income' | 'savings';
export type GoalScope = 'default' | 'month_override';

export interface GoalTypeState {
  goal_type: GoalType;
  default_amount_minor: number | null;
  override_amount_minor: number | null;
  effective_amount_minor: number | null;
  effective_source: GoalScope | null;
}

export interface MonthlyGoalsResponse {
  month: string;
  currency: string;
  items: GoalTypeState[];
}

export interface SavedGoal {
  goal_type: GoalType;
  scope: GoalScope;
  month: string | null;
  amount_minor: number;
  currency: string;
}

// Create payload: amount is a non-negative magnitude (server owns the sign).
export interface CreateTemplateInput {
  name: string;
  amount: string;
  category_id: string;
  cadence?: string;
  next_expected_date: string;
  counts_in_projection?: boolean;
  note?: string | null;
}

export interface PatchTemplateInput {
  name?: string;
  amount?: string;
  category_id?: string;
  cadence?: string;
  next_expected_date?: string;
  counts_in_projection?: boolean;
  is_active?: boolean;
  note?: string | null;
}

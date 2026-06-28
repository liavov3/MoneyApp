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

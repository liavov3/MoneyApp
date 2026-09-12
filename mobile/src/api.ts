// Minimal backend client. Base URL + dev bearer token both come from
// EXPO_PUBLIC_* env (mobile/.env). Auth is config-only for now — no login
// screen; the backend still requires the token, so it is sent on every request.
import type {
  CategoryOut,
  CreateTemplateInput,
  GoalScope,
  GoalType,
  HomeResponse,
  MerchantSuggestionsResponse,
  MonthlyGoalsResponse,
  PatchTemplateInput,
  PatchTransactionInput,
  QuickAddInput,
  QuickAddResponse,
  RecentMerchant,
  RecurringListResponse,
  SavedGoal,
  TemplateOut,
  TransactionListResponse,
  TransactionOut,
} from './types';

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const API = `${BASE_URL}/api/v1`;
const API_TOKEN = (process.env.EXPO_PUBLIC_API_TOKEN ?? '').trim();

export const apiBaseUrl = BASE_URL;
export const hasToken = API_TOKEN.length > 0;

export class ApiError extends Error {
  status: number;
  code?: string;
  fieldErrors: Array<{ field: string; code: string }>;
  constructor(message: string, status: number, code?: string, fieldErrors: Array<{ field: string; code: string }> = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }

  fieldCode(field: string) { return this.fieldErrors.find((item) => item.field === field)?.code; }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (!API_TOKEN) throw new ApiError('missing_token', 401, 'unauthorized');

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const resp = await fetch(`${API}${path}`, {
      method,
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (resp.status === 204) return undefined as T;
    if (!resp.ok) {
      let code: string | undefined;
      let fieldErrors: Array<{ field: string; code: string }> = [];
      try {
        const error = (await resp.json())?.error;
        code = error?.code;
        if (Array.isArray(error?.field_errors)) fieldErrors = error.field_errors.filter(
          (item: unknown): item is { field: string; code: string } =>
            typeof item === 'object' && item !== null && 'field' in item && 'code' in item &&
            typeof item.field === 'string' && typeof item.code === 'string',
        ).map(({ field, code }: { field: string; code: string }) => ({ field, code }));
      } catch {
        /* Preserve HTTP status even when the error response is not JSON. */
      }
      throw new ApiError(`http_${resp.status}`, resp.status, code, fieldErrors);
    }
    return (await resp.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    // No automatic write retry: a lost response may follow a committed save.
    throw new ApiError('network_error', 0);
  } finally {
    clearTimeout(timeout);
  }
}

export const getHome = (month?: string) =>
  request<HomeResponse>('GET', `/home${month ? `?month=${encodeURIComponent(month)}` : ''}`);

export const getCategories = () => request<{ items: CategoryOut[] }>('GET', '/categories');

export const getRecentMerchants = (limit = 8) =>
  request<{ items: RecentMerchant[] }>('GET', `/merchants/recent?limit=${limit}`);

export const getMerchantSuggestions = (query: string, limit = 8) =>
  request<MerchantSuggestionsResponse>(
    'GET',
    `/merchants/suggestions?query=${encodeURIComponent(query)}&limit=${limit}`,
  );

export const quickAdd = (input: QuickAddInput) =>
  request<QuickAddResponse>('POST', '/transactions/quick-add', input);

export const listTransactions = (params: { month?: string; cursor?: string; limit?: number; category_id?: string; uncategorized?: boolean } = {}) => {
  const q = new URLSearchParams();
  if (params.month) q.set('month', params.month);
  if (params.cursor) q.set('cursor', params.cursor);
  if (params.limit) q.set('limit', String(params.limit));
  if (params.category_id) q.set('category_id', params.category_id);
  if (params.uncategorized) q.set('uncategorized', 'true');
  const qs = q.toString();
  return request<TransactionListResponse>('GET', `/transactions${qs ? `?${qs}` : ''}`);
};

export const getTransaction = (id: string) =>
  request<TransactionOut>('GET', `/transactions/${id}`);

export const patchTransaction = (id: string, body: PatchTransactionInput) =>
  request<TransactionOut>('PATCH', `/transactions/${id}`, body);

export const deleteTransaction = (id: string) =>
  request<void>('DELETE', `/transactions/${id}`);

// Recurring expense templates (API_CONTRACT §12). Projection-only on the
// backend — these never create a transaction row.
export const listRecurring = (active?: boolean) =>
  request<RecurringListResponse>(
    'GET',
    `/recurring-templates${active === undefined ? '' : `?active=${active}`}`,
  );

export const createRecurring = (body: CreateTemplateInput) =>
  request<TemplateOut>('POST', '/recurring-templates', body);

export const patchRecurring = (id: string, body: PatchTemplateInput) =>
  request<TemplateOut>('PATCH', `/recurring-templates/${id}`, body);

export const deleteRecurring = (id: string) =>
  request<void>('DELETE', `/recurring-templates/${id}`);

export const getMonthlyGoals = (month: string) =>
  request<MonthlyGoalsResponse>('GET', `/monthly-goals?month=${encodeURIComponent(month)}`);

export const putMonthlyGoal = (body: {
  goal_type: GoalType;
  scope: GoalScope;
  month?: string;
  amount_minor: number;
}) => request<SavedGoal>('PUT', '/monthly-goals', body);

export const deleteMonthlyGoal = (params: {
  goal_type: GoalType;
  scope: GoalScope;
  month?: string;
}) => {
  const q = new URLSearchParams({ goal_type: params.goal_type, scope: params.scope });
  if (params.month) q.set('month', params.month);
  return request<void>('DELETE', `/monthly-goals?${q.toString()}`);
};

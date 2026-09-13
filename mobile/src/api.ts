// Authenticated client: credentials are supplied at runtime and never bundled.
import { session } from './session';
import type { SessionTransport } from './sessionStore';
import type {
  CategorizeInput,
  CategorizeResponse,
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

export function createApiClient(transport: SessionTransport) {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const credentials = transport.getConnection();
    if (!credentials) throw new ApiError('missing_session', 401, 'unauthorized');

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const resp = await fetch(`${credentials.baseUrl}/api/v1${path}`, {
        method,
        redirect: 'error',
        signal: controller.signal,
        credentials: credentials.token === null ? 'same-origin' : 'omit',
        cache: 'no-store',
        headers: {
          ...(credentials.token === null
            ? { 'X-MoneySaver-Client': 'web' }
            : { Authorization: `Bearer ${credentials.token}` }),
          Accept: 'application/json',
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (transport.getConnection() !== credentials) {
        // A write may have committed before the session changed. Keep it
        // ambiguous unless the server explicitly rejected authentication.
        throw new ApiError('session_changed', method === 'GET' || resp.status === 401 ? 401 : 0);
      }
      if (resp.status === 401) transport.invalidate(credentials);
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
      const data = (await resp.json()) as T;
      if (transport.getConnection() !== credentials) throw new ApiError('session_changed', method === 'GET' ? 401 : 0);
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      // No automatic write retry: a lost response may follow a committed save.
      throw new ApiError('network_error', 0);
    } finally {
      clearTimeout(timeout);
    }
  }

  const getHome = (month?: string) =>
    request<HomeResponse>('GET', `/home${month ? `?month=${encodeURIComponent(month)}` : ''}`);

  const getCategories = () => request<{ items: CategoryOut[] }>('GET', '/categories');

  const getRecentMerchants = (limit = 8) =>
    request<{ items: RecentMerchant[] }>('GET', `/merchants/recent?limit=${limit}`);

  const getMerchantSuggestions = (query: string, limit = 8) =>
    request<MerchantSuggestionsResponse>(
      'GET',
      `/merchants/suggestions?query=${encodeURIComponent(query)}&limit=${limit}`,
    );

  const quickAdd = (input: QuickAddInput) =>
    request<QuickAddResponse>('POST', '/transactions/quick-add', input);

  const listTransactions = (params: { month?: string; cursor?: string; limit?: number; category_id?: string; uncategorized?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.month) q.set('month', params.month);
    if (params.cursor) q.set('cursor', params.cursor);
    if (params.limit) q.set('limit', String(params.limit));
    if (params.category_id) q.set('category_id', params.category_id);
    if (params.uncategorized) q.set('uncategorized', 'true');
    const qs = q.toString();
    return request<TransactionListResponse>('GET', `/transactions${qs ? `?${qs}` : ''}`);
  };

  const getTransaction = (id: string) =>
    request<TransactionOut>('GET', `/transactions/${id}`);

  const patchTransaction = (id: string, body: PatchTransactionInput) =>
    request<TransactionOut>('PATCH', `/transactions/${id}`, body);

  const deleteTransaction = (id: string) =>
    request<void>('DELETE', `/transactions/${id}`);

  const categorizeTransaction = (id: string, body: CategorizeInput) =>
    request<CategorizeResponse>('POST', `/transactions/${id}/categorize`, body);

  // Recurring expense templates (API_CONTRACT §12). Projection-only on the
  // backend — these never create a transaction row.
  const listRecurring = (active?: boolean) =>
    request<RecurringListResponse>(
      'GET',
      `/recurring-templates${active === undefined ? '' : `?active=${active}`}`,
    );

  const createRecurring = (body: CreateTemplateInput) =>
    request<TemplateOut>('POST', '/recurring-templates', body);

  const patchRecurring = (id: string, body: PatchTemplateInput) =>
    request<TemplateOut>('PATCH', `/recurring-templates/${id}`, body);

  const deleteRecurring = (id: string) =>
    request<void>('DELETE', `/recurring-templates/${id}`);

  const getMonthlyGoals = (month: string) =>
    request<MonthlyGoalsResponse>('GET', `/monthly-goals?month=${encodeURIComponent(month)}`);

  const putMonthlyGoal = (body: {
    goal_type: GoalType;
    scope: GoalScope;
    month?: string;
    amount_minor: number;
  }) => request<SavedGoal>('PUT', '/monthly-goals', body);

  const deleteMonthlyGoal = (params: {
    goal_type: GoalType;
    scope: GoalScope;
    month?: string;
  }) => {
    const q = new URLSearchParams({ goal_type: params.goal_type, scope: params.scope });
    if (params.month) q.set('month', params.month);
    return request<void>('DELETE', `/monthly-goals?${q.toString()}`);
  };

  return { getHome, getCategories, getRecentMerchants, getMerchantSuggestions, quickAdd, listTransactions, getTransaction, patchTransaction, deleteTransaction, categorizeTransaction, listRecurring, createRecurring, patchRecurring, deleteRecurring, getMonthlyGoals, putMonthlyGoal, deleteMonthlyGoal };
}

export const { getHome, getCategories, getRecentMerchants, getMerchantSuggestions, quickAdd, listTransactions, getTransaction, patchTransaction, deleteTransaction, categorizeTransaction, listRecurring, createRecurring, patchRecurring, deleteRecurring, getMonthlyGoals, putMonthlyGoal, deleteMonthlyGoal } = createApiClient(session);

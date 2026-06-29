// Minimal backend client. Base URL + dev bearer token both come from
// EXPO_PUBLIC_* env (mobile/.env). Auth is config-only for now — no login
// screen; the backend still requires the token, so it is sent on every request.
import type {
  CategoryOut,
  HomeResponse,
  MerchantSuggestionsResponse,
  QuickAddInput,
  QuickAddResponse,
  RecentMerchant,
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
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (!API_TOKEN) throw new ApiError('missing_token', 401, 'unauthorized');

  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // Network/DNS/refused — generic load error (no PII).
    throw new ApiError('network_error', 0);
  }

  if (resp.status === 204) return undefined as T;
  if (!resp.ok) {
    let code: string | undefined;
    try {
      code = (await resp.json())?.error?.code;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(`http_${resp.status}`, resp.status, code);
  }
  return (await resp.json()) as T;
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

export const listTransactions = (params: { month?: string; cursor?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.month) q.set('month', params.month);
  if (params.cursor) q.set('cursor', params.cursor);
  if (params.limit) q.set('limit', String(params.limit));
  const qs = q.toString();
  return request<TransactionListResponse>('GET', `/transactions${qs ? `?${qs}` : ''}`);
};

export const getTransaction = (id: string) =>
  request<TransactionOut>('GET', `/transactions/${id}`);

export const deleteTransaction = (id: string) =>
  request<void>('DELETE', `/transactions/${id}`);

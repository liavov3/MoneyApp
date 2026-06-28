// Minimal backend client. Base URL from EXPO_PUBLIC_API_URL (no hardcoded prod
// URL). The bearer token lives in SecureStore, set once via the token gate.
import * as SecureStore from 'expo-secure-store';

import type { CategoryOut, HomeResponse } from './types';

const BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const API = `${BASE_URL}/api/v1`;
const TOKEN_KEY = 'moneysaver_api_token';

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}
export async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token.trim());
}
export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

async function authedGet<T>(path: string): Promise<T> {
  const token = await getToken();
  if (!token) throw new ApiError('missing_token', 401, 'unauthorized');

  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
    });
  } catch {
    // Network/DNS/refused — surfaced as a generic load error (no PII).
    throw new ApiError('network_error', 0);
  }

  if (!resp.ok) {
    // Backend uses { error: { code, message, ... } }; never trust it for UI copy.
    let code: string | undefined;
    try {
      code = (await resp.json())?.error?.code;
    } catch {
      /* ignore non-JSON bodies */
    }
    throw new ApiError(`http_${resp.status}`, resp.status, code);
  }
  return (await resp.json()) as T;
}

export function getHome(month?: string): Promise<HomeResponse> {
  return authedGet<HomeResponse>(`/home${month ? `?month=${encodeURIComponent(month)}` : ''}`);
}

export function getCategories(): Promise<{ items: CategoryOut[] }> {
  return authedGet<{ items: CategoryOut[] }>('/categories');
}

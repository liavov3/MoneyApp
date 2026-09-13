import { ConnectionError, normalizeBaseUrl, type Credentials } from './sessionStore';

export class SignInError extends Error {
  constructor(public status: number) { super('sign_in_failed'); }
}

export function createAuthClient(web: boolean) {
  async function request(baseUrl: string, path: string, credentials?: Credentials | null, body?: unknown) {
    const controller = new AbortController();
    // A free host can take about a minute to wake. Never retry a write silently.
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/v1/auth/${path}`, {
        method: body === undefined && path === 'session' ? 'GET' : 'POST',
        credentials: web ? 'same-origin' : 'omit',
        cache: 'no-store', redirect: 'error', signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(web ? { 'X-MoneySaver-Client': 'web' } : {}),
          ...(credentials?.token ? { Authorization: `Bearer ${credentials.token}` } : {}),
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) throw new SignInError(response.status);
      if (response.status === 204) return null;
      const data = await response.json();
      if (data?.authenticated !== true || typeof data.expires_at !== 'string' ||
        !Number.isFinite(Date.parse(data.expires_at))) throw new SignInError(0);
      return data;
    } catch (error) {
      if (error instanceof SignInError || error instanceof ConnectionError) throw error;
      throw new SignInError(0);
    } finally { clearTimeout(timeout); }
  }

  return {
    login: async (baseUrl: string, username: string, password: string): Promise<Credentials> => {
      const data = await request(baseUrl, 'login', null, { username: username.trim(), password, client: web ? 'web' : 'native' });
      if (!web && !/^[A-Za-z0-9_-]{43}$/.test(data?.access_token ?? '')) throw new SignInError(0);
      return Object.freeze({ baseUrl: normalizeBaseUrl(baseUrl), token: web ? null : data.access_token });
    },
    restore: async (baseUrl: string, saved: Credentials | null): Promise<Credentials | null> => {
      if (!web && !saved) return null;
      try {
        await request(baseUrl, 'session', web ? null : saved);
        return Object.freeze({ baseUrl: normalizeBaseUrl(baseUrl), token: web ? null : saved!.token });
      } catch (error) {
        if (error instanceof SignInError && error.status === 401) return null;
        throw error;
      }
    },
    logout: async (baseUrl: string, credentials: Credentials | null): Promise<void> => {
      if (!web && !credentials) return;
      await request(baseUrl, 'logout', credentials);
    },
  };
}

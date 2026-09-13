export type Credentials = Readonly<{ baseUrl: string; token: string | null }>;
export type CredentialStorage = {
  read: () => Promise<unknown>;
  write: (credentials: Credentials) => Promise<void>;
  remove: () => Promise<void>;
};

export type SessionAuth = {
  login: (baseUrl: string, username: string, password: string) => Promise<Credentials>;
  restore: (baseUrl: string, saved: Credentials | null) => Promise<Credentials | null>;
  logout: (baseUrl: string, credentials: Credentials | null) => Promise<void>;
};
type Snapshot = {
  status: 'loading' | 'disconnected' | 'connected' | 'expired';
  busy: boolean;
  error: 'storage_read' | 'storage_clear' | 'logout' | null;
  version: number;
};

export class ConnectionError extends Error {
  constructor(public code: 'invalid_url' | 'invalid_token' | 'storage_write' | 'busy') {
    super(code);
  }
}

export function normalizeBaseUrl(value: string): string {
  try {
    const url = new URL(value.trim());
    const host = url.hostname.toLowerCase();
    const parts = host.split('.').map(Number);
    const ipv4 = parts.length === 4 && parts.every((n) => Number.isInteger(n) && n >= 0 && n <= 255);
    const local = host === 'localhost' || host === '[::1]' || (ipv4 && (
      parts[0] === 127 || parts[0] === 10 ||
      (parts[0] === 192 && parts[1] === 168) ||
      (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
    ));
    if (url.username || url.password || url.search || url.hash ||
      (url.protocol !== 'https:' && !(url.protocol === 'http:' && local))) throw new Error();
    return url.href.replace(/\/+$/, '');
  } catch {
    throw new ConnectionError('invalid_url');
  }
}

function credentialsFor(baseUrl: string, token: string): Credentials {
  const cleaned = token.trim();
  if (!/^[A-Za-z0-9_-]{43}$/.test(cleaned)) throw new ConnectionError('invalid_token');
  return Object.freeze({ baseUrl: normalizeBaseUrl(baseUrl), token: cleaned });
}

// Credentials remain outside the observable UI snapshot. Every request captures
// one credential object; its identity also guards against late responses.
export function createSessionStore(baseUrl: string, storage: CredentialStorage, auth: SessionAuth) {
  let connection: Credentials | null = null;
  let snapshot: Snapshot = { status: 'loading', busy: false, error: null, version: 0 };
  let restoring: Promise<void> | null = null;
  const listeners = new Set<() => void>();
  const publish = (next: Partial<Snapshot>) => {
    snapshot = { ...snapshot, ...next };
    listeners.forEach((listener) => listener());
  };
  const activate = (credentials: Credentials) => {
    connection = credentials;
    publish({ status: 'connected', busy: false, error: null, version: snapshot.version + 1 });
  };
  const removeStored = async () => {
    try { await storage.remove(); }
    catch { publish({ error: 'storage_clear' }); }
    finally { publish({ busy: false }); }
  };
  return {
    getSnapshot: () => snapshot,
    getConnection: () => connection,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    restore: () => {
      if (restoring) return restoring;
      if (snapshot.busy || (snapshot.status !== 'loading' && snapshot.error !== 'storage_read')) return Promise.resolve();
      publish({ status: 'loading', busy: true, error: null });
      restoring = (async () => {
        try {
          const saved = await storage.read();
          let credentials: Credentials | null = null;
          if (saved !== null && typeof saved === 'object' && 'baseUrl' in saved && 'token' in saved &&
            typeof saved.baseUrl === 'string' && typeof saved.token === 'string') {
            try {
              const candidate = credentialsFor(saved.baseUrl, saved.token);
              if (candidate.baseUrl === normalizeBaseUrl(baseUrl)) credentials = candidate;
            } catch { /* Discard malformed or legacy static credentials. */ }
          }
          if (saved !== null && !credentials) await storage.remove();
          const restored = await auth.restore(baseUrl, credentials);
          if (restored) { activate(restored); return; }
          await storage.remove();
          publish({ status: 'disconnected', busy: false });
        } catch {
          publish({ status: 'disconnected', busy: false, error: 'storage_read' });
        } finally { restoring = null; }
      })();
      return restoring;
    },
    signIn: async (username: string, password: string) => {
      if (snapshot.busy || connection) throw new ConnectionError('busy');
      publish({ busy: true, error: null });
      try {
        const credentials = await auth.login(baseUrl, username, password);
        try { await storage.write(credentials); }
        catch {
          try { await auth.logout(baseUrl, credentials); } catch { /* No local activation. */ }
          throw new ConnectionError('storage_write');
        }
        activate(credentials);
      } finally { publish({ busy: false }); }
    },
    disconnect: async () => {
      if (snapshot.busy) return;
      publish({ busy: true, error: null });
      try { await auth.logout(baseUrl, connection); }
      catch {
        publish({ busy: false, error: 'logout' });
        return;
      }
      connection = null;
      publish({ status: 'disconnected', busy: true, error: null });
      await removeStored();
    },
    invalidate: (expected: Credentials) => {
      if (connection !== expected) return;
      connection = null;
      publish({ status: 'expired', busy: true, error: null });
      void removeStored();
    },
  };
}

export type SessionTransport = Pick<ReturnType<typeof createSessionStore>, 'getConnection' | 'invalidate'>;

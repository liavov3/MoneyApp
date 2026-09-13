import { createSessionStore } from './sessionStore';
import { createAuthClient } from './authClient';
import { apiBaseUrl, webSession } from './sessionPlatform';

// Only the non-secret server address is build configuration.
export const configuredApiUrl = apiBaseUrl;

// Lazy platform loading keeps the state machine independent of native modules.
export const session = createSessionStore(configuredApiUrl, {
  read: async () => (await import('./credentialStorage')).credentialStorage.read(),
  write: async (credentials) => (await import('./credentialStorage')).credentialStorage.write(credentials),
  remove: async () => (await import('./credentialStorage')).credentialStorage.remove(),
}, createAuthClient(webSession));

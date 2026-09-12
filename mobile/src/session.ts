import { createSessionStore } from './sessionStore';

// Only the non-secret server address is build configuration.
export const configuredApiUrl = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

// Lazy platform loading keeps the state machine independent of native modules.
export const session = createSessionStore(configuredApiUrl, {
  read: async () => (await import('./credentialStorage')).credentialStorage.read(),
  write: async (credentials) => (await import('./credentialStorage')).credentialStorage.write(credentials),
  remove: async () => (await import('./credentialStorage')).credentialStorage.remove(),
});

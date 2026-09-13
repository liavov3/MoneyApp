import type { CredentialStorage } from './sessionStore';

// The browser manages the HttpOnly session cookie. JavaScript never receives
// or persists a web session secret, password, or financial payload.
export const credentialStorage: CredentialStorage = {
  read: async () => null,
  write: async () => {},
  remove: async () => {},
};

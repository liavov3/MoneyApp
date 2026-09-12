import type { CredentialStorage } from './sessionStore';

// Web is a temporary preview. Never persist bearer tokens in browser storage.
export const credentialStorage: CredentialStorage = {
  read: async () => null,
  write: async () => {},
  remove: async () => {},
};

import * as SecureStore from 'expo-secure-store';
import type { CredentialStorage } from './sessionStore';

const key = 'moneyapp.connection.v1';
const options: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export const credentialStorage: CredentialStorage = {
  read: async () => {
    const value = await SecureStore.getItemAsync(key, options);
    return value === null ? null : JSON.parse(value);
  },
  write: (credentials) => SecureStore.setItemAsync(key, JSON.stringify(credentials), options),
  remove: () => SecureStore.deleteItemAsync(key, options),
};

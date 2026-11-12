// SPDX-License-Identifier: Apache-2.0
// Native modules are replaced with in-memory fakes; tests never touch a keychain or a notification centre.
const mockStore = new Map<string, string>();
jest.mock('expo-secure-store', () => ({
  AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 0,
  getItemAsync: jest.fn(async (k: string) => mockStore.get(k) ?? null),
  setItemAsync: jest.fn(async (k: string, v: string) => void mockStore.set(k, v)),
  deleteItemAsync: jest.fn(async (k: string) => void mockStore.delete(k)),
}));
jest.mock('expo-notifications', () => ({
  setNotificationHandler: jest.fn(),
  setNotificationChannelAsync: jest.fn(async () => null),
  getPermissionsAsync: jest.fn(async () => ({ granted: true, canAskAgain: true })),
  requestPermissionsAsync: jest.fn(async () => ({ granted: true })),
  scheduleNotificationAsync: jest.fn(async () => 'id'),
  setBadgeCountAsync: jest.fn(async () => true),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  getDevicePushTokenAsync: jest.fn(async () => ({ type: 'ios', data: 'test-token' })),
  unregisterForNotificationsAsync: jest.fn(async () => undefined),
  AndroidImportance: { HIGH: 4 },
}));

// Native passkeys and the CSPRNG: no authenticator in tests; randomness from Node's WebCrypto.
jest.mock('react-native-passkey', () => ({
  Passkey: { isSupported: jest.fn(() => false), get: jest.fn(), create: jest.fn() },
}));
jest.mock('expo-crypto', () => ({
  getRandomBytes: (n: number) => globalThis.crypto.getRandomValues(new Uint8Array(n)),
}));

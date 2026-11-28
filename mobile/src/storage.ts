// SPDX-License-Identifier: Apache-2.0
// The connection (hub URL + token) lives in the OS secure store: the iOS Keychain
// and Android Keystore-backed storage, via expo-secure-store. Never AsyncStorage.
import * as SecureStore from 'expo-secure-store';

/**
 * `token` is the bearer sent now. With `auth: 'passkey'` it is a short-lived session token from
 * `POST /v1/auth/login` (§12.6), renewed with `refreshToken` or this phone's device key (lib/device).
 * Without `auth` it is a v0 static token typed by hand.
 */
export type LiveConnection = {
  mode: 'live';
  hubUrl: string;
  token: string;
  auth?: 'token' | 'passkey';
  refreshToken?: string;
  expiresAt?: string;
  /** Hub and principal identity verified at sign-in, for reopening its local app data. */
  localAccount?: string;
};

/** Only a real hub. A stored demo entry from an older build (`mode: 'mock'`) loads as signed out. */
export type Connection = LiveConnection;

const KEY = 'onemind.connection.v1';
const OPTS: SecureStore.SecureStoreOptions = {
  // Readable after the first unlock since boot, so a background refresh can use it later;
  // never synced to iCloud Keychain or restored onto another device.
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
};

function parse(raw: string | null): Connection | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<Connection> & { hubUrl?: string };
    if (v.mode === 'live' && typeof v.token === 'string' && typeof v.hubUrl === 'string') {
      const c: LiveConnection = { mode: 'live', hubUrl: v.hubUrl, token: v.token };
      const l = v as Partial<LiveConnection>;
      if (l.auth === 'passkey' || l.auth === 'token') c.auth = l.auth;
      if (typeof l.refreshToken === 'string') c.refreshToken = l.refreshToken;
      if (typeof l.expiresAt === 'string') c.expiresAt = l.expiresAt;
      if (typeof l.localAccount === 'string') c.localAccount = l.localAccount;
      return c;
    }
  } catch {
    /* corrupt entry: treat as signed out */
  }
  return null;
}

export async function loadConnection(): Promise<Connection | null> {
  try {
    return parse(await SecureStore.getItemAsync(KEY, OPTS));
  } catch {
    return null;
  }
}

export async function saveConnection(c: Connection): Promise<void> {
  await SecureStore.setItemAsync(KEY, JSON.stringify(c), OPTS);
}

/** Small helpers for other secure-store records (device key, device link, push registration). */
export async function loadSecret(key: string): Promise<string | null> {
  try {
    return await readSecret(key);
  } catch {
    return null;
  }
}

/** Read a record where a storage failure must be distinct from an absent value. */
export function readSecret(key: string): Promise<string | null> {
  return SecureStore.getItemAsync(key, OPTS);
}

export async function saveSecret(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value, OPTS);
}

export async function deleteSecret(key: string): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(key, OPTS);
  } catch {
    /* nothing stored */
  }
}

export async function clearConnection(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEY, OPTS);
  } catch {
    /* nothing stored */
  }
}

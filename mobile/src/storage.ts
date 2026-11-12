// SPDX-License-Identifier: Apache-2.0
// The connection (hub URL + token) lives in the OS secure store: the iOS Keychain
// and Android Keystore-backed storage, via expo-secure-store. Never AsyncStorage.
import * as SecureStore from 'expo-secure-store';

export type Connection =
  | { mode: 'live'; hubUrl: string; token: string }
  | { mode: 'mock'; token: string };

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
    if (v.mode === 'mock' && typeof v.token === 'string') return { mode: 'mock', token: v.token };
    if (v.mode === 'live' && typeof v.token === 'string' && typeof v.hubUrl === 'string')
      return { mode: 'live', hubUrl: v.hubUrl, token: v.token };
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

export async function clearConnection(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEY, OPTS);
  } catch {
    /* nothing stored */
  }
}

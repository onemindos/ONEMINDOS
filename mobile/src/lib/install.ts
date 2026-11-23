// SPDX-License-Identifier: Apache-2.0
// This app install as one device on the box (My devices, #715).
//
// The hub's My devices list groups a person's sign-ins, passkeys and push registrations into devices.
// A free-text name cannot do that: two phones both called "Android phone" (the default) would merge,
// and a phone renamed in Settings would split. So the app makes one random install id the first time
// it runs, keeps it in the secure store (this device only: never synced to a cloud keychain or restored
// onto another phone), and sends it with every sign-in, passkey and push registration. The name is kept
// beside it, so every credential carries the same name too; renaming here changes what the box shows.
//
// The install id is not a secret and not a credential: it only says "these credentials came from one
// install". It survives Disconnect, so signing in again shows up as the same device.
import * as Crypto from 'expo-crypto';
import { useEffect, useState } from 'react';
import { loadSecret, saveSecret } from '../storage';
import { deviceInfo, toB64url } from './device';

export interface ThisPhone {
  /** 22 base64url characters (128 random bits); what the hub's `install_id` fields accept. */
  installId: string;
  /** The name every credential from this install carries. */
  name: string;
}

const KEY = 'onemind.install.v1';
const ID = /^[A-Za-z0-9_-]{16,64}$/;

let cached: ThisPhone | undefined;
let loading: Promise<ThisPhone> | undefined;
const subscribers = new Set<(p: ThisPhone) => void>();

function clean(name: string): string {
  return deviceInfo(name).name; // trimmed, at most 64 characters, the platform default when empty
}

async function load(random: (n: number) => Uint8Array): Promise<ThisPhone> {
  try {
    const v = JSON.parse((await loadSecret(KEY)) ?? 'null') as Partial<ThisPhone> | null;
    if (v && typeof v.installId === 'string' && ID.test(v.installId)) {
      return { installId: v.installId, name: clean(typeof v.name === 'string' ? v.name : '') };
    }
  } catch {
    // unreadable: make a new one below
  }
  const made = { installId: toB64url(random(16)), name: clean('') };
  await saveSecret(KEY, JSON.stringify(made)).catch(() => undefined);
  return made;
}

/** This install's id and name: read from the secure store, or made once. */
export function loadThisPhone(random: (n: number) => Uint8Array = (n) => Crypto.getRandomBytes(n)): Promise<ThisPhone> {
  if (cached) return Promise.resolve(cached);
  loading ??= load(random).then((p) => (cached = p));
  return loading;
}

/** Rename this phone; the next sign-in, passkey and push registration carry the new name. */
export async function renameThisPhone(name: string): Promise<ThisPhone> {
  const next = { ...(await loadThisPhone()), name: clean(name) };
  cached = next;
  await saveSecret(KEY, JSON.stringify(next)).catch(() => undefined);
  subscribers.forEach((f) => f(next));
  return next;
}

/** The same ThisPhone in every screen; undefined until the secure store answers. */
export function useThisPhone(): ThisPhone | undefined {
  const [phone, setPhone] = useState<ThisPhone | undefined>(cached);
  useEffect(() => {
    let live = true;
    subscribers.add(setPhone);
    void loadThisPhone().then((p) => live && setPhone(p));
    return () => {
      live = false;
      subscribers.delete(setPhone);
    };
  }, []);
  return phone;
}

/** Tests only: forget the in-memory copy (the secure store fake is reset separately). */
export function resetThisPhoneForTests(): void {
  cached = undefined;
  loading = undefined;
}

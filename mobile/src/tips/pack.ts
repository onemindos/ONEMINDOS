// SPDX-License-Identifier: Apache-2.0
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils.js';
import { NetworkError, OneMindError, type components, type OneMind } from '@onemind/sdk';
import { getRandomBytes } from 'expo-crypto';
import { Directory, File, Paths } from '../device/files';
import { loadSecret, saveSecret } from '../storage';

type Tip = Pick<components['schemas']['TipView'], 'id' | 'title' | 'body'>;
type Pack = { scope: string; tips: Tip[] };
type AvailablePack = { tips: Tip[]; offline: boolean };

const cacheName = 'pack-v1.json';
const saltKey = 'onemind.tips.cache-salt.v1';
const cacheDirectory = () => new Directory(Paths.cache, 'onemind-tips');

export function tipsScope(hubUrl: string, token: string) {
  // Offline startup may not know the principal yet. Scope the screen to the remembered bearer.
  return bytesToHex(sha256(utf8ToBytes(JSON.stringify([hubUrl, token]))));
}

let salt: Promise<string> | undefined;

async function cacheScope(connection: string) {
  // A random device secret keeps the cached fingerprint from being used to guess a bearer.
  salt ??= (async () => {
    const stored = await loadSecret(saltKey);
    if (stored) return stored;
    const generated = bytesToHex(getRandomBytes(32));
    await saveSecret(saltKey, generated);
    return generated;
  })();
  try {
    return bytesToHex(sha256(utf8ToBytes(JSON.stringify([await salt, connection]))));
  } catch {
    salt = undefined;
  }
}

function tipShape(value: unknown): value is Tip {
  if (typeof value !== 'object' || value === null) return false;
  const tip = value as Partial<Tip>;
  return typeof tip.id === 'string' && typeof tip.title === 'string' && typeof tip.body === 'string';
}

async function readPack(): Promise<Pack | undefined> {
  try {
    const file = new File(cacheDirectory(), cacheName);
    if (!file.exists) return;
    const data = JSON.parse(await file.text()) as Partial<Pack> | null;
    if (typeof data?.scope === 'string' && Array.isArray(data.tips) && data.tips.every(tipShape)) {
      return { scope: data.scope, tips: data.tips };
    }
  } catch {
    // The OS may evict its cache. Treat unreadable or incomplete data as a miss.
  }
}

async function savePack(pack: Pack) {
  const dir = cacheDirectory();
  dir.create({ idempotent: true, intermediates: true });
  const temp = new File(dir, bytesToHex(getRandomBytes(16)) + '.tmp');
  try {
    await temp.write(JSON.stringify(pack));
    await temp.move(new File(dir, cacheName), { overwrite: true });
  } catch (error) {
    if (temp.exists) temp.delete();
    throw error;
  }
}

export async function loadTips(client: OneMind, connection: string): Promise<AvailablePack> {
  const cache = cacheScope(connection);
  try {
    const response = await client.tips.list();
    if (!Array.isArray(response?.tips) || !response.tips.every(tipShape)) throw new Error('Invalid Tips pack');
    const tips = response.tips.map(({ id, title, body }) => ({ id, title, body }));
    // The cached pack contains authored text only. The person's progress stays on the hub.
    const scope = await cache;
    if (scope) await savePack({ scope, tips }).catch(() => undefined);
    return { tips, offline: false };
  } catch (error) {
    const scope = await cache;
    if (scope && error instanceof NetworkError) {
      const cached = await readPack();
      if (cached?.scope === scope) return { tips: cached.tips, offline: true };
    }
    if (scope && error instanceof OneMindError && [401, 403, 404, 409].includes(error.status)) {
      // Once the hub withdraws access or removes Tips, stop offering its last pack offline.
      if ((await readPack())?.scope === scope) {
        try { new File(cacheDirectory(), cacheName).delete(); } catch { /* cache may already be absent */ }
      }
    }
    throw error;
  }
}

export function tipsError(error: unknown) {
  if (error instanceof NetworkError) return 'No Tips pack is saved for this connection. Open Tips while connected to your hub.';
  if (error instanceof OneMindError) {
    if (error.status === 401 || error.status === 403) return 'Your account cannot view Tips right now.';
    if (error.status === 404 || error.status === 409) return 'Tips is unavailable on this hub.';
  }
  return 'Could not load Tips from your hub.';
}

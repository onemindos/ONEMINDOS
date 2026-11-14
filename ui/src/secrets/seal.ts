// SPDX-License-Identifier: Apache-2.0
// Sealed input (contract §12.1; construction in core/onemind_core/appsecrets/crypto.py):
//   shared = X25519(ephemeral, box)
//   k      = HKDF-SHA256(shared, salt = epk ‖ box_pub, info = "onemind sealed-input v1")
//   ct     = nonce(12) ‖ AES-256-GCM(k, nonce, JSON, aad = "onemind/app-secrets/<app-id>")
// Every step is WebCrypto, so the plaintext never leaves this function unencrypted.
import type { SealedInput, SecretValues, SecretsPublicKey } from './types';

const INFO = new TextEncoder().encode('onemind sealed-input v1');

export const sealedContext = (appId: string) => `onemind/app-secrets/${appId}`;

export function b64u(bytes: Uint8Array): string {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function unb64u(text: string): Uint8Array {
  const s = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length);
  out.set(a);
  out.set(b, a.length);
  return out;
}

/** Seal raw bytes to a 32-byte X25519 public key. */
export async function seal(boxPublic: Uint8Array, plaintext: Uint8Array, context: string, keyId?: string, subtle: SubtleCrypto = globalThis.crypto.subtle): Promise<SealedInput> {
  if (boxPublic.length !== 32) throw new Error('the box public key must be 32 bytes');
  const box = await subtle.importKey('raw', boxPublic as BufferSource, { name: 'X25519' }, false, []);
  const eph = (await subtle.generateKey({ name: 'X25519' }, true, ['deriveBits'])) as CryptoKeyPair;
  const epk = new Uint8Array(await subtle.exportKey('raw', eph.publicKey));
  const shared = await subtle.deriveBits({ name: 'X25519', public: box } as unknown as AlgorithmIdentifier, eph.privateKey, 256);
  const hkdf = await subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  const key = await subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: concat(epk, boxPublic) as BufferSource, info: INFO as BufferSource },
    hkdf,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt'],
  );
  const nonce = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(
    await subtle.encrypt({ name: 'AES-GCM', iv: nonce as BufferSource, additionalData: new TextEncoder().encode(context) as BufferSource }, key, plaintext as BufferSource),
  );
  return { alg: 'X25519-AES256GCM', ...(keyId ? { kid: keyId } : {}), epk: b64u(epk), ct: b64u(concat(nonce, ct)) };
}

/** Seal the form's values for one app, given GET /v1/secrets/public-key. */
export function sealValues(pk: SecretsPublicKey, appId: string, values: SecretValues, subtle?: SubtleCrypto): Promise<SealedInput> {
  const body = new TextEncoder().encode(JSON.stringify({ values }));
  return seal(unb64u(pk.key), body, sealedContext(appId), pk.key_id, subtle);
}

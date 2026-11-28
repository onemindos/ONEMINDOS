// SPDX-License-Identifier: Apache-2.0
// Sealed install secrets on the phone (contract §12.1, issue #528). The same construction as the
// dashboard (ui/src/secrets/seal.ts) and the box (core/onemind_core/appsecrets/crypto.py):
//   shared = X25519(ephemeral, box)
//   k      = HKDF-SHA256(shared, salt = epk ‖ box_pub, info = "onemind sealed-input v1")
//   ct     = nonce(12) ‖ AES-256-GCM(k, nonce, JSON, aad = "onemind/app-secrets/<app-id>")
// React Native has no WebCrypto X25519, so the key agreement and HKDF use @noble (already a
// dependency) and AES-GCM uses the platform's own implementation through expo-crypto. The typed
// values exist in clear only inside this function; what leaves it is the sealed box.
import { x25519 } from '@noble/curves/ed25519.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { utf8ToBytes } from '@noble/hashes/utils.js';
import { AESEncryptionKey, AESSealedData, aesEncryptAsync, getRandomBytes } from 'expo-crypto';
import type { SealedInput, SecretValues, SecretsPublicKey } from '../api/types';
import { fromB64url, toB64url } from './device';

const INFO = utf8ToBytes('onemind sealed-input v1');
const NONCE_BYTES = 12;

export const sealedContext = (appId: string) => `onemind/app-secrets/${appId}`;

/** AES-256-GCM encrypt: returns ciphertext ‖ 16-byte tag. A seam so tests can run without the native module. */
export type AesGcm = (key: Uint8Array, nonce: Uint8Array, plaintext: Uint8Array, aad: Uint8Array) => Promise<Uint8Array>;

/** Randomness for the ephemeral key and the nonce. A seam for tests; defaults to the platform CSPRNG. */
export type RandomBytes = (n: number) => Uint8Array;

/** The platform AES-GCM (Android Keystore provider / Apple CryptoKit) through expo-crypto. */
export const nativeAesGcm: AesGcm = async (key, nonce, plaintext, aad) => {
  const k = await AESEncryptionKey.import(key);
  const sealed: AESSealedData = await aesEncryptAsync(plaintext, k, { nonce: { bytes: nonce }, tagLength: 16, additionalData: aad });
  return sealed.ciphertext({ includeTag: true, encoding: 'bytes' });
};

function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

/** Seal raw bytes to the box's 32-byte X25519 public key. */
export async function seal(
  boxPublic: Uint8Array,
  plaintext: Uint8Array,
  context: string,
  keyId?: string,
  aes: AesGcm = nativeAesGcm,
  random: RandomBytes = getRandomBytes,
): Promise<SealedInput> {
  if (boxPublic.length !== 32) throw new Error('the box public key must be 32 bytes');
  const eph = random(32);
  try {
    const epk = x25519.getPublicKey(eph);
    // A low-order box key gives an all-zero shared secret: refuse, as the box does on its side.
    // @noble already rejects it; the check below stays in case that ever changes.
    let shared: Uint8Array;
    try {
      shared = x25519.getSharedSecret(eph, boxPublic);
    } catch {
      throw new Error('the box public key is not usable');
    }
    if (shared.every((b) => b === 0)) throw new Error('the box public key is not usable');
    const key = hkdf(sha256, shared, concat(epk, boxPublic), INFO, 32);
    const nonce = random(NONCE_BYTES);
    const ct = await aes(key, nonce, plaintext, utf8ToBytes(context));
    key.fill(0);
    shared.fill(0);
    return { alg: 'X25519-AES256GCM', ...(keyId ? { kid: keyId } : {}), epk: toB64url(epk), ct: toB64url(concat(nonce, ct)) };
  } finally {
    eph.fill(0);
  }
}

/** Seal the form's values for one app, given `GET /v1/secrets/public-key`. */
export async function sealValues(pk: SecretsPublicKey, appId: string, values: SecretValues, aes?: AesGcm, random?: RandomBytes): Promise<SealedInput> {
  if (pk.alg !== 'X25519' || pk.sealed_alg !== 'X25519-AES256GCM') throw new Error(`the box offers ${pk.alg}/${pk.sealed_alg}, which this app cannot seal to`);
  const body = utf8ToBytes(JSON.stringify({ values }));
  try {
    return await seal(fromB64url(pk.key), body, sealedContext(appId), pk.key_id, aes, random);
  } finally {
    body.fill(0);
  }
}

// SPDX-License-Identifier: Apache-2.0
// The browser side of sealed input, opened here the way the box opens it
// (core/onemind_core/appsecrets/crypto.py StoreKey.open_sealed). Keys are made per run.
import { describe, expect, it } from 'vitest';
import { b64u, sealValues, sealedContext, unb64u } from './seal';

const subtle = globalThis.crypto.subtle;
const enc = (s: string) => new TextEncoder().encode(s);

async function boxKeys() {
  const pair = (await subtle.generateKey({ name: 'X25519' }, true, ['deriveBits'])) as CryptoKeyPair;
  return { raw: new Uint8Array(await subtle.exportKey('raw', pair.publicKey)), privateKey: pair.privateKey };
}

async function open(sealed: { epk: string; ct: string }, box: Awaited<ReturnType<typeof boxKeys>>, context: string): Promise<string> {
  const epk = unb64u(sealed.epk);
  const pub = await subtle.importKey('raw', epk as BufferSource, { name: 'X25519' }, false, []);
  const shared = await subtle.deriveBits({ name: 'X25519', public: pub } as unknown as AlgorithmIdentifier, box.privateKey, 256);
  const hkdf = await subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  const salt = new Uint8Array([...epk, ...box.raw]);
  const key = await subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt, info: enc('onemind sealed-input v1') }, hkdf, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  const blob = unb64u(sealed.ct);
  const pt = await subtle.decrypt({ name: 'AES-GCM', iv: blob.slice(0, 12), additionalData: enc(context) }, key, blob.slice(12));
  return new TextDecoder().decode(pt);
}

describe('sealValues', () => {
  it('produces the contract shape and opens with the box key for that app only', async () => {
    const box = await boxKeys();
    const value = 'sk-test-' + Math.random().toString(36).slice(2);
    const sealed = await sealValues({ alg: 'X25519', key: b64u(box.raw), key_id: 'sk_test', sealed_alg: 'X25519-AES256GCM' }, 'vault-like', {
      'vault-like-credentials': { PROVIDER_API_KEY: value },
    });
    expect(sealed.alg).toBe('X25519-AES256GCM');
    expect(sealed.kid).toBe('sk_test');
    expect(unb64u(sealed.epk)).toHaveLength(32);
    expect(JSON.stringify(sealed)).not.toContain(value);
    expect(JSON.parse(await open(sealed, box, sealedContext('vault-like')))).toEqual({ values: { 'vault-like-credentials': { PROVIDER_API_KEY: value } } });
    await expect(open(sealed, box, sealedContext('other-app'))).rejects.toThrow();
  });

  it('uses a fresh ephemeral key and nonce every time', async () => {
    const box = await boxKeys();
    const pk = { alg: 'X25519' as const, key: b64u(box.raw), key_id: 'k', sealed_alg: 'X25519-AES256GCM' as const };
    const a = await sealValues(pk, 'x-app', { s: { K: 'abcd' } });
    const b = await sealValues(pk, 'x-app', { s: { K: 'abcd' } });
    expect(a.epk).not.toBe(b.epk);
    expect(a.ct).not.toBe(b.ct);
  });

  it('round-trips base64url', () => {
    const bytes = Uint8Array.from({ length: 33 }, (_, i) => (i * 37) % 256);
    expect(unb64u(b64u(bytes))).toEqual(bytes);
    expect(b64u(bytes)).not.toMatch(/[+/=]/);
  });
});

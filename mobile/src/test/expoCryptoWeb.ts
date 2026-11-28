// SPDX-License-Identifier: Apache-2.0
// expo-crypto for tests that seal (#528): its AES-GCM is native, so this stands in with Node's WebCrypto.
// Use as `jest.mock('expo-crypto', () => jest.requireActual('../test/expoCryptoWeb').expoCryptoWeb())`.
export function expoCryptoWeb() {
  const subtle = globalThis.crypto.subtle;
  class AESEncryptionKey {
    constructor(readonly raw: Uint8Array) {}
    static async import(bytes: Uint8Array) {
      return new AESEncryptionKey(bytes);
    }
  }
  type Opts = { nonce: { bytes: Uint8Array }; tagLength: number; additionalData: Uint8Array };
  return {
    getRandomBytes: (n: number) => globalThis.crypto.getRandomValues(new Uint8Array(n)),
    AESEncryptionKey,
    aesEncryptAsync: jest.fn(async (pt: Uint8Array, key: AESEncryptionKey, opts: Opts) => {
      const k = await subtle.importKey('raw', key.raw as BufferSource, 'AES-GCM', false, ['encrypt']);
      const ct = new Uint8Array(await subtle.encrypt(
        { name: 'AES-GCM', iv: opts.nonce.bytes as BufferSource, additionalData: opts.additionalData as BufferSource, tagLength: opts.tagLength * 8 },
        k, pt as BufferSource,
      ));
      return { ciphertext: async ({ includeTag }: { includeTag: boolean }) => (includeTag ? ct : ct.slice(0, -16)) };
    }),
  };
}

/** A box key pair made per run, and a decrypt that opens a sealed input the way the box does. */
export async function testBox() {
  const subtle = globalThis.crypto.subtle;
  const enc = (s: string) => new TextEncoder().encode(s);
  const pair = (await subtle.generateKey({ name: 'X25519' }, true, ['deriveBits'])) as CryptoKeyPair;
  const raw = new Uint8Array(await subtle.exportKey('raw', pair.publicKey));
  const unb64u = (t: string) => Uint8Array.from(atob(t.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (t.length % 4)) % 4)), (c) => c.charCodeAt(0));
  const b64u = (b: Uint8Array) => btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  async function open(sealed: { epk: string; ct: string }, context: string): Promise<string> {
    const epk = unb64u(sealed.epk);
    const pub = await subtle.importKey('raw', epk as BufferSource, { name: 'X25519' }, false, []);
    const shared = await subtle.deriveBits({ name: 'X25519', public: pub } as unknown as AlgorithmIdentifier, pair.privateKey, 256);
    const hkdf = await subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
    const key = await subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array([...epk, ...raw]), info: enc('onemind sealed-input v1') },
      hkdf, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
    const blob = unb64u(sealed.ct);
    return new TextDecoder().decode(await subtle.decrypt({ name: 'AES-GCM', iv: blob.slice(0, 12), additionalData: enc(context) }, key, blob.slice(12)));
  }
  return { raw, publicKey: { alg: 'X25519' as const, key: b64u(raw), key_id: 'sk_test', sealed_alg: 'X25519-AES256GCM' as const }, open };
}

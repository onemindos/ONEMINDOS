// SPDX-License-Identifier: Apache-2.0
// The phone side of sealed input (#528), opened with Node's WebCrypto the way the box opens it
// (core/onemind_core/appsecrets/crypto.py StoreKey.open_sealed). Keys are made per run.
import * as ExpoCrypto from 'expo-crypto';
import { testBox } from '../test/expoCryptoWeb';
import { fromB64url, toB64url } from './device';
import { nativeAesGcm, sealValues, sealedContext, type AesGcm } from './seal';

// expo-crypto's AES is native: WebCrypto stands in, so nativeAesGcm's wiring (nonce, AAD, tag) is what is checked.
jest.mock('expo-crypto', () => jest.requireActual('../test/expoCryptoWeb').expoCryptoWeb());

const pkOf = (raw: Uint8Array) => ({ alg: 'X25519' as const, key: toB64url(raw), key_id: 'sk_test', sealed_alg: 'X25519-AES256GCM' as const });

describe('sealValues on the phone', () => {
  it('produces the contract shape and opens with the box key for that app only', async () => {
    const box = await testBox();
    const value = 'sk-test-' + Math.random().toString(36).slice(2);
    const sealed = await sealValues(box.publicKey, 'vault-like', { 'vault-like-credentials': { PROVIDER_API_KEY: value } });
    expect(sealed.alg).toBe('X25519-AES256GCM');
    expect(sealed.kid).toBe('sk_test');
    expect(fromB64url(sealed.epk)).toHaveLength(32);
    expect(JSON.stringify(sealed)).not.toContain(value);
    expect(JSON.parse(await box.open(sealed, sealedContext('vault-like')))).toEqual({ values: { 'vault-like-credentials': { PROVIDER_API_KEY: value } } });
    await expect(box.open(sealed, sealedContext('other-app'))).rejects.toThrow();
  });

  it('passes a 12-byte nonce, the app-bound AAD and a 16-byte tag to the platform AES', async () => {
    const box = await testBox();
    await sealValues(box.publicKey, 'ollama', { s: { K: 'abcd' } });
    const call = jest.mocked(ExpoCrypto.aesEncryptAsync).mock.calls.at(-1)! as unknown as [Uint8Array, unknown, { nonce: { bytes: Uint8Array }; tagLength: number; additionalData: Uint8Array }];
    expect(call[2].nonce.bytes).toHaveLength(12);
    expect(call[2].tagLength).toBe(16);
    expect(new TextDecoder().decode(call[2].additionalData)).toBe('onemind/app-secrets/ollama');
  });

  it('uses a fresh ephemeral key and nonce every time', async () => {
    const box = await testBox();
    const a = await sealValues(box.publicKey, 'x-app', { s: { K: 'abcd' } });
    const b = await sealValues(box.publicKey, 'x-app', { s: { K: 'abcd' } });
    expect(a.epk).not.toBe(b.epk);
    expect(a.ct).not.toBe(b.ct);
  });

  it('refuses a short or low-order key and an algorithm it cannot seal to, and never calls AES', async () => {
    const aes: AesGcm = jest.fn(nativeAesGcm);
    await expect(sealValues(pkOf(new Uint8Array(31)), 'x', { s: { K: 'abcd' } }, aes)).rejects.toThrow(/32 bytes/);
    // An all-zero (low-order) box key gives an all-zero shared secret: refused, as the box does.
    await expect(sealValues(pkOf(new Uint8Array(32)), 'x', { s: { K: 'abcd' } }, aes)).rejects.toThrow(/not usable/);
    await expect(sealValues({ ...pkOf(new Uint8Array(32)), sealed_alg: 'RSA' as never }, 'x', { s: { K: 'abcd' } }, aes)).rejects.toThrow(/cannot seal/);
    expect(aes).not.toHaveBeenCalled();
  });
});

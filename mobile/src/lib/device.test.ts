// SPDX-License-Identifier: Apache-2.0
import { p256 } from '@noble/curves/nist.js';
import { Features, OP } from '../api/client';
import { ApiError, type DeviceRequestBody } from '../api/types';
import { v0Api } from '../test/fakes';
import { dpopProof, forgetDevice, fromB64url, keyFromSecret, loadKey, loadLink, pollDevice, renewWithDevice, requestDevice, thumbprint, toB64url } from './device';

const seed = (n: number) => Uint8Array.from({ length: n }, (_, i) => (i * 7 + 3) & 255);
const subtle = globalThis.crypto.subtle;
const text = (b: Uint8Array) => new TextDecoder().decode(b);

describe('base64url', () => {
  it('matches RFC 4648 vectors and round-trips', () => {
    const enc = (s: string) => toB64url(new TextEncoder().encode(s));
    expect([enc('f'), enc('fo'), enc('foo'), enc('foobar')]).toEqual(['Zg', 'Zm8', 'Zm9v', 'Zm9vYmFy']);
    expect(toB64url(Uint8Array.from([251, 255]))).toBe('-_8');
    expect(text(fromB64url('Zm9vYmFy'))).toBe('foobar');
  });
});

describe('device key and DPoP (RFC 7638, RFC 9449)', () => {
  const key = keyFromSecret(p256.utils.randomSecretKey(seed(48)));

  it('exports a P-256 JWK and its thumbprint, checked with WebCrypto', async () => {
    expect(key.jwk).toMatchObject({ kty: 'EC', crv: 'P-256' });
    expect(fromB64url(key.jwk.x)).toHaveLength(32);
    const canonical = `{"crv":"P-256","kty":"EC","x":"${key.jwk.x}","y":"${key.jwk.y}"}`;
    const digest = new Uint8Array(await subtle.digest('SHA-256', new TextEncoder().encode(canonical)));
    expect(thumbprint(key.jwk)).toBe(toB64url(digest));
  });

  it('signs a proof that an independent ES256 verifier accepts', async () => {
    const proof = dpopProof(key, { htm: 'POST', htu: 'https://onemind.local:8443/v1/devices/token', nonce: 'n1', iat: 1700000000, jti: 'j1' });
    const [h, p, sig] = proof.split('.') as [string, string, string];
    expect(JSON.parse(text(fromB64url(h)))).toEqual({ typ: 'dpop+jwt', alg: 'ES256', jwk: key.jwk });
    expect(JSON.parse(text(fromB64url(p)))).toEqual({ jti: 'j1', htm: 'POST', htu: 'https://onemind.local:8443/v1/devices/token', iat: 1700000000, nonce: 'n1' });
    const pub = await subtle.importKey('jwk', { ...key.jwk, ext: true }, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
    const ok = await subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, pub, fromB64url(sig) as BufferSource, new TextEncoder().encode(`${h}.${p}`));
    expect(ok).toBe(true);
  });
});

describe('device request: an owner-approved action (clients.md §4.4)', () => {
  beforeEach(async () => forgetDevice());

  it('sends the public key and device facts, remembers the request, and learns the owner\'s answer', async () => {
    let body: DeviceRequestBody | undefined;
    const api = v0Api({
      deviceRequest: async (b) => {
        body = b;
        return { id: 'dreq_1', state: 'pending', action_id: 'act-9', poll_code: 'pc' };
      },
      deviceRequestStatus: async (id, code) => {
        expect([id, code]).toEqual(['dreq_1', 'pc']);
        return { id: 'dreq_1', state: 'active', device_id: 'dev_7k2m', one_time: { refresh_token: 'rt1' } };
      },
    });
    const link = await requestDevice(api, 'https://h', 'Zeus phone', { random: seed, now: 0 });
    expect(body).toMatchObject({ name: 'Zeus phone', kind: 'phone', jwk: (await loadKey())!.jwk });
    expect(JSON.stringify(body)).not.toMatch(/"d"/); // never the private key
    expect(link).toMatchObject({ state: 'pending', actionId: 'act-9' });
    const after = await pollDevice(api, link);
    expect(after).toMatchObject({ state: 'active', deviceId: 'dev_7k2m', refreshToken: 'rt1' });
    expect(await loadLink('https://h')).toEqual(after);
    expect(await loadLink('https://other')).toBeUndefined();
  });

  it('renews the sign-in with a DPoP proof, retrying once with the server nonce, and rotates the refresh token', async () => {
    const api0 = v0Api({
      deviceRequest: async () => ({ id: 'd', state: 'active', one_time: { refresh_token: 'rt1' } }),
    });
    await requestDevice(api0, 'https://h', 'p', { random: seed });
    const proofs: string[] = [];
    const deviceToken = jest.fn(async (proof: string, rt: string) => {
      proofs.push(proof);
      expect(rt).toBe('rt1');
      if (proofs.length === 1) throw new ApiError(401, 'unauthenticated', 'use_dpop_nonce', { dpopNonce: 'srv-nonce' });
      return { access_token: 'at', expires_at: 'x', refresh_token: 'rt2' };
    });
    const r = await renewWithDevice(v0Api({ deviceToken }), new Features([OP.deviceToken], 'openapi'), 'https://h');
    expect(r?.access_token).toBe('at');
    expect(JSON.parse(text(fromB64url(proofs[1]!.split('.')[1]!))).nonce).toBe('srv-nonce');
    expect((await loadLink('https://h'))?.refreshToken).toBe('rt2');
  });

  it('does nothing on a hub without device tokens or for a phone that is not approved', async () => {
    expect(await renewWithDevice(v0Api(), Features.none(), 'https://h')).toBeUndefined();
    const pending = v0Api({ deviceRequest: async () => ({ id: 'd', state: 'pending' }) });
    await requestDevice(pending, 'https://h', 'p', { random: seed });
    expect(await renewWithDevice(pending, new Features([OP.deviceToken], 'openapi'), 'https://h')).toBeUndefined();
  });
});

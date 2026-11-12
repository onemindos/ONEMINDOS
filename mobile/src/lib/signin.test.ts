// SPDX-License-Identifier: Apache-2.0
import type { FetchLike } from '../api/client';
import { hubOffersPasskeys, passkeySignIn, SignInError } from './signin';
import type { Passkeys } from './webauthn';

const assertion = { id: 'cred', clientDataJSON: 'cd', authenticatorData: 'ad', signature: 'sig', userHandle: 'uh' };

function hub(paths: string[]): { fn: FetchLike; calls: Array<{ url: string; body?: unknown; auth?: string }> } {
  const calls: Array<{ url: string; body?: unknown; auth?: string }> = [];
  const fn: FetchLike = async (url, init) => {
    const h = (init?.headers ?? {}) as Record<string, string>;
    calls.push({ url, body: init?.body ? JSON.parse(init.body as string) : undefined, auth: h.Authorization });
    if (url.endsWith('/openapi.json')) return new Response(JSON.stringify({ paths: Object.fromEntries(paths.map((p) => [p, { post: {} }])) }), { status: 200 });
    if (url.endsWith('/v1/auth/login/options'))
      return new Response(JSON.stringify({ publicKey: { challenge: 'Q2g+', rpId: 'onemind.local', allowCredentials: [] } }), { status: 200 });
    if (url.endsWith('/v1/auth/login'))
      return new Response(JSON.stringify({ access_token: 'at', expires_at: '2030-01-01T00:00:00Z', refresh_token: 'rt' }), { status: 200 });
    return new Response('{}', { status: 404 });
  };
  return { fn, calls };
}

const passkeys = (): Passkeys & { get: jest.Mock } => ({ supported: () => true, get: jest.fn(async () => assertion), create: jest.fn() });

describe('passkey sign-in (§12.6)', () => {
  it('signs the hub challenge and returns a renewable passkey session; no token is typed or sent first', async () => {
    const { fn, calls } = hub(['/v1/auth/login/options', '/v1/auth/login']);
    const pk = passkeys();
    const c = await passkeySignIn('https://onemind.local:8443/', pk, { fetchFn: fn, deviceName: 'Pixel' });
    expect(c).toEqual({ mode: 'live', hubUrl: 'https://onemind.local:8443', token: 'at', auth: 'passkey', expiresAt: '2030-01-01T00:00:00Z', refreshToken: 'rt' });
    expect(pk.get).toHaveBeenCalledWith({ challenge: 'Q2g-', rpId: 'onemind.local', timeout: 60_000, userVerification: 'required' });
    expect(calls.at(-1)).toMatchObject({ url: 'https://onemind.local:8443/v1/auth/login', body: { webauthn: assertion, client: 'mobile', device_name: 'Pixel' } });
    expect(calls.every((x) => x.auth === undefined)).toBe(true);
  });

  it('says plainly when the hub has no passkey sign-in yet', async () => {
    const { fn } = hub([]);
    await expect(passkeySignIn('https://h', passkeys(), { fetchFn: fn })).rejects.toBeInstanceOf(SignInError);
    expect(await hubOffersPasskeys('https://h', fn)).toBe(false);
  });

  it('refuses before contacting the authenticator when the phone has none', async () => {
    const { fn } = hub(['/v1/auth/login/options']);
    await expect(passkeySignIn('https://h', undefined, { fetchFn: fn })).rejects.toMatchObject({ kind: 'not_supported' });
  });
});

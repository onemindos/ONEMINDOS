// SPDX-License-Identifier: Apache-2.0
// Passkey sign-in (contract §12.6, CORE-SEC-2): the hub sends a challenge, the phone's authenticator
// signs it after Face ID / fingerprint, the hub answers with a short-lived bearer and a refresh token.
// No password and no token is typed or shown. The session is then validated and saved like any other.
import { HttpApi, normalizeHubUrl, OP, type FetchLike } from '../api/client';
import type { LiveConnection } from '../storage';
import { PasskeyError, requestOptionsFrom, rpIdFor, type Passkeys } from './webauthn';

export class SignInError extends Error {
  constructor(
    readonly kind: 'no_passkeys_on_hub' | 'insecure',
    message: string,
  ) {
    super(message);
    this.name = 'SignInError';
  }
}

/**
 * Plain HTTP to anything but this device. §12.7: a hub with passkey sign-in serves HTTPS on :8443 and
 * accepts HTTP only on loopback, so a passkey sign-in over plain HTTP elsewhere is a misconfigured hub or
 * someone on the network path, and its answer (a bearer and a long-lived refresh token) would travel in clear.
 */
export function plainHttpOffDevice(hubUrl: string): boolean {
  try {
    const u = new URL(hubUrl);
    return u.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname);
  } catch {
    return false;
  }
}

/** Does this hub offer passkey sign-in? Reads /openapi.json (open, no token). */
export async function hubOffersPasskeys(hubUrl: string, fetchFn?: FetchLike): Promise<boolean> {
  const api = new HttpApi({ baseUrl: normalizeHubUrl(hubUrl), fetchFn });
  return (await api.features()).has(OP.loginOptions);
}

export async function passkeySignIn(rawHubUrl: string, passkeys: Passkeys | undefined, o: { deviceName?: string; fetchFn?: FetchLike } = {}): Promise<LiveConnection> {
  const hubUrl = normalizeHubUrl(rawHubUrl);
  if (plainHttpOffDevice(hubUrl))
    throw new SignInError('insecure', "Passkey sign-in needs the hub's https:// address (port 8443). Over plain HTTP your session could be copied on the network.");
  const api = new HttpApi({ baseUrl: hubUrl, fetchFn: o.fetchFn });
  if (!(await api.features()).has(OP.loginOptions))
    throw new SignInError('no_passkeys_on_hub', 'This hub does not offer passkey sign-in yet. Use an access token below.');
  if (!passkeys || !passkeys.supported()) throw new PasskeyError('not_supported', 'no platform authenticator');
  const options = await api.loginOptions();
  const webauthn = await passkeys.get(requestOptionsFrom(options, rpIdFor(hubUrl)));
  const r = await api.login({ webauthn, client: 'mobile', ...(o.deviceName ? { device_name: o.deviceName } : {}) });
  return {
    mode: 'live',
    hubUrl,
    token: r.access_token,
    auth: 'passkey',
    expiresAt: r.expires_at,
    ...(r.refresh_token ? { refreshToken: r.refresh_token } : {}),
  };
}

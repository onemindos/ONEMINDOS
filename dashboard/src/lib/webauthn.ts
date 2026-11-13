// SPDX-License-Identifier: Apache-2.0
// Browser side of WebAuthn: turns the gateway's JSON options (base64url strings) into the
// binary form the browser wants, and the browser's answer back into the JSON the gateway reads
// (same shape as core/onemind_core/identity/signin.html). The private key never leaves the device.

export const b64u = (buf: ArrayBuffer): string => {
  let s = '';
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};
export const unb64u = (s: string): Uint8Array<ArrayBuffer> => {
  const pad = '==='.slice((s.length + 3) % 4);
  const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/') + pad);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
};

export const webauthnSupported = (): boolean => typeof window !== 'undefined' && !!window.PublicKeyCredential && !!navigator.credentials;

type Json = Record<string, unknown>;

function decodeOptions(pk: Json): Json {
  const out: Json = { ...pk, challenge: unb64u(String(pk.challenge)) };
  if (pk.user && typeof pk.user === 'object') out.user = { ...(pk.user as Json), id: unb64u(String((pk.user as Json).id)) };
  for (const k of ['excludeCredentials', 'allowCredentials']) {
    const list = pk[k];
    if (Array.isArray(list)) out[k] = list.map((c: Json) => ({ ...c, id: unb64u(String(c.id)) }));
  }
  return out;
}

/** The credential as the gateway expects it (WebAuthn JSON). */
export function credentialJson(c: PublicKeyCredential): Json {
  const r = c.response as AuthenticatorAttestationResponse & AuthenticatorAssertionResponse;
  const response: Json = { clientDataJSON: b64u(r.clientDataJSON) };
  if (r.attestationObject) {
    response.attestationObject = b64u(r.attestationObject);
    response.transports = typeof r.getTransports === 'function' ? r.getTransports() : [];
  }
  if (r.authenticatorData) {
    response.authenticatorData = b64u(r.authenticatorData);
    response.signature = b64u(r.signature);
    if (r.userHandle) response.userHandle = b64u(r.userHandle);
  }
  return { id: c.id, rawId: b64u(c.rawId), type: c.type, response };
}

/** Ask the authenticator to sign in. Rejects when the person cancels. */
export async function getPasskey(publicKey: Json): Promise<Json> {
  const c = (await navigator.credentials.get({ publicKey: decodeOptions(publicKey) as unknown as PublicKeyCredentialRequestOptions })) as PublicKeyCredential | null;
  if (!c) throw new Error('No passkey was chosen.');
  return credentialJson(c);
}

/** Ask the authenticator to create a passkey. */
export async function createPasskey(publicKey: Json): Promise<Json> {
  const c = (await navigator.credentials.create({ publicKey: decodeOptions(publicKey) as unknown as PublicKeyCredentialCreationOptions })) as PublicKeyCredential | null;
  if (!c) throw new Error('No passkey was created.');
  return credentialJson(c);
}

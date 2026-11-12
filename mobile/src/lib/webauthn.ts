// SPDX-License-Identifier: Apache-2.0
// WebAuthn glue between the gateway (§12.4 approve-options, §12.6 login and passkey registration)
// and the phone's platform authenticator (Face ID, Touch ID, fingerprint, screen lock).
// Pure functions: the native call itself is behind the `Passkeys` interface (lib/passkeys.ts).
import type { LoginOptions, RegisterOptions } from '../api/client';
import type {
  ApproveOptions,
  WebAuthnAssertion,
  WebAuthnAttestation,
  WebAuthnCreationOptions,
  WebAuthnRequestOptions,
} from '../api/types';

/** What can go wrong at the authenticator, in words the screens can use. */
export type PasskeyFailure = 'cancelled' | 'not_supported' | 'not_configured' | 'no_credentials' | 'failed';

export class PasskeyError extends Error {
  constructor(
    readonly kind: PasskeyFailure,
    message: string,
  ) {
    super(message);
    this.name = 'PasskeyError';
  }
}

/** The platform authenticator. Implemented natively in lib/passkeys.ts; faked in tests. */
export interface Passkeys {
  supported(): boolean;
  get(options: WebAuthnRequestOptions): Promise<WebAuthnAssertion>;
  create(options: WebAuthnCreationOptions): Promise<WebAuthnAttestation>;
}

/** Standard base64 or base64url → unpadded base64url (what the platform APIs expect). */
export function b64url(v: string): string {
  return v.trim().replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** The relying-party id the hub most likely uses when it does not say: its host name. */
export function rpIdFor(hubUrl: string | undefined): string | undefined {
  if (!hubUrl) return undefined;
  try {
    return new URL(hubUrl).hostname;
  } catch {
    return undefined;
  }
}

type CredList = WebAuthnRequestOptions['allowCredentials'];
const creds = (list: CredList | undefined): CredList | undefined =>
  list?.map((c) => ({ id: b64url(c.id), type: 'public-key' as const, ...(c.transports ? { transports: c.transports } : {}) }));

/**
 * Assertion options from an approve-options or login-options answer. The gateway may send bare
 * WebAuthn JSON or wrap it in `publicKey`; `rpId` falls back to the hub's host name.
 * User verification is always required: an approval is "you, now", not "this phone is unlocked".
 */
export function requestOptionsFrom(opts: ApproveOptions | LoginOptions, fallbackRpId: string | undefined): WebAuthnRequestOptions {
  const pk = opts.publicKey ?? {};
  const challenge = pk.challenge ?? opts.challenge;
  const rpId = pk.rpId ?? opts.rpId ?? fallbackRpId;
  if (!challenge) throw new PasskeyError('failed', 'The hub sent no passkey challenge.');
  if (!rpId) throw new PasskeyError('failed', 'The hub did not say which name the passkey belongs to.');
  const allow = creds(pk.allowCredentials ?? opts.allowCredentials);
  return {
    challenge: b64url(challenge),
    rpId,
    timeout: pk.timeout ?? 60_000,
    userVerification: 'required',
    ...(allow?.length ? { allowCredentials: allow } : {}),
  };
}

/** Creation options for "add a passkey on this phone"; a discoverable credential with user verification. */
export function creationOptionsFrom(opts: RegisterOptions, fallbackRpId: string | undefined): WebAuthnCreationOptions {
  const src = { ...opts, ...(opts.publicKey ?? {}) } as Partial<WebAuthnCreationOptions>;
  if (!src.challenge || !src.user?.id || !src.user.name) throw new PasskeyError('failed', 'The hub sent incomplete passkey options.');
  const rpId = src.rp?.id ?? fallbackRpId;
  if (!rpId) throw new PasskeyError('failed', 'The hub did not say which name the passkey belongs to.');
  return {
    challenge: b64url(src.challenge),
    rp: { id: rpId, name: src.rp?.name ?? 'OneMind' },
    user: { id: b64url(src.user.id), name: src.user.name, displayName: src.user.displayName ?? src.user.name },
    pubKeyCredParams: src.pubKeyCredParams?.length ? src.pubKeyCredParams : [{ type: 'public-key', alg: -7 }],
    timeout: src.timeout ?? 120_000,
    ...(src.excludeCredentials?.length ? { excludeCredentials: creds(src.excludeCredentials) } : {}),
    authenticatorSelection: {
      residentKey: 'required',
      requireResidentKey: true,
      userVerification: 'required',
      ...(src.authenticatorSelection?.authenticatorAttachment ? { authenticatorAttachment: src.authenticatorSelection.authenticatorAttachment } : {}),
    },
    attestation: src.attestation ?? 'none',
  };
}

/** A platform assertion → the §12.4 `webauthn` body (base64url strings, nothing else). */
export function assertionFrom(r: {
  id: string;
  response: { clientDataJSON: string; authenticatorData: string; signature: string; userHandle?: string | null };
}): WebAuthnAssertion {
  return {
    id: b64url(r.id),
    clientDataJSON: b64url(r.response.clientDataJSON),
    authenticatorData: b64url(r.response.authenticatorData),
    signature: b64url(r.response.signature),
    ...(r.response.userHandle ? { userHandle: b64url(r.response.userHandle) } : {}),
  };
}

export function attestationFrom(r: {
  id: string;
  response: { clientDataJSON: string; attestationObject: string; transports?: string[] };
}): WebAuthnAttestation {
  return {
    id: b64url(r.id),
    clientDataJSON: b64url(r.response.clientDataJSON),
    attestationObject: b64url(r.response.attestationObject),
    ...(r.response.transports?.length ? { transports: r.response.transports } : {}),
  };
}

/** Plain words for a passkey failure; `where` is the relying-party id when known. */
export function passkeyMessage(e: PasskeyError, where?: string): string {
  switch (e.kind) {
    case 'cancelled':
      return 'Cancelled. Nothing was approved or changed.';
    case 'no_credentials':
      return `This phone has no passkey for ${where ?? 'this hub'}. Add one in Settings, or approve on the dashboard.`;
    case 'not_configured':
      return `This build of the app is not linked to ${where ?? 'this hub'} for passkeys yet (see mobile/README.md, "Passkeys"). Approve on the dashboard for now.`;
    case 'not_supported':
      return 'This phone cannot use a passkey here (passkeys need iOS 16 or Android 14 and a screen lock). Approve on the dashboard.';
    default:
      return `The passkey did not work: ${e.message}`;
  }
}

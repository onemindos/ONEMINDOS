// SPDX-License-Identifier: Apache-2.0
// The phone's hardware approval key (#703, gateway side #702). An EC P-256 key in the Android Keystore
// (StrongBox when the phone has one) signs one approval inside the system biometric prompt. The hub keeps
// only the public key, and checks the signature, the plan hash, expiry and single use; the phone checks
// first so it never signs something the card does not show, and never sends a "success" without a
// signature that verifies against the key it enrolled.
import { p256 } from '@noble/curves/nist.js';
import { utf8ToBytes } from '@noble/hashes/utils.js';
import { approvalKeyNative, type ApprovalKeyNative, type SecurityLevel } from '../../modules/onemind-approval-key';
import type { OneMindApi } from '../api/client';
import { ApiError, type Action, type ApproveOptions, type DeviceSignature } from '../api/types';
import { fromB64url } from '../lib/device';
import { deleteSecret, loadSecret, saveSecret } from '../storage';

/** Must match core/onemind_core/identity/approver_keys.py `PAYLOAD_TAG` and `signing_payload`. */
export const PAYLOAD_TAG = 'onemind-approve-v1';

export function signingPayload(challenge: string, actionId: string, actionSha256: string, planSha256: string | null | undefined): string {
  return [PAYLOAD_TAG, actionId, actionSha256, planSha256 || '-', challenge].join('\n');
}

export type ApprovalKeyFailure =
  | 'not_on_phone'
  | 'no_biometric'
  | 'cancelled'
  | 'lockout'
  | 'invalidated'
  | 'plan_changed'
  | 'payload_mismatch'
  | 'replay'
  | 'bad_signature'
  | 'failed';

export class ApprovalKeyError extends Error {
  constructor(
    readonly kind: ApprovalKeyFailure,
    message: string,
  ) {
    super(message);
    this.name = 'ApprovalKeyError';
  }
}

/** What the person reads when the key could not sign. */
export function approvalKeyMessage(e: ApprovalKeyError): string {
  switch (e.kind) {
    case 'invalidated':
      return 'A new fingerprint or face was added to this phone, so its approval key no longer works. Nothing was approved. Set up the approval key again under Approvals.';
    case 'cancelled':
      return 'Cancelled. Nothing was approved.';
    case 'lockout':
      return 'Too many tries. Unlock the phone with your fingerprint or face first, then approve again.';
    case 'no_biometric':
      return 'This phone has no strong fingerprint or face unlock set up. Add one in the phone settings first.';
    case 'plan_changed':
      return 'The plan changed since this card was loaded. Nothing was approved; check the new version.';
    case 'payload_mismatch':
      return 'The hub asked this phone to sign something other than the card shows. Nothing was signed or approved.';
    case 'replay':
      return 'The hub sent a challenge this phone already signed. Nothing was approved; try again.';
    case 'bad_signature':
      return 'The approval key gave no valid signature. Nothing was approved.';
    default:
      return `The approval key could not sign: ${e.message}. Nothing was approved.`;
  }
}

const NATIVE_KIND: Record<string, ApprovalKeyFailure> = {
  ERR_CANCELLED: 'cancelled',
  ERR_NO_KEY: 'invalidated',
  ERR_KEY_INVALIDATED: 'invalidated',
  ERR_NO_BIOMETRIC: 'no_biometric',
  ERR_LOCKOUT: 'lockout',
};

function fromNative(e: unknown): ApprovalKeyError {
  const code = (e as { code?: string } | null)?.code;
  const message = (e as { message?: string } | null)?.message ?? String(e);
  return new ApprovalKeyError((code && NATIVE_KIND[code]) || 'failed', message);
}

// SubjectPublicKeyInfo header for an id-ecPublicKey / prime256v1 uncompressed point (RFC 5480).
const SPKI_P256 = '3059301306072a8648ce3d020106082a8648ce3d030107034200';

/** The 65-byte uncompressed point inside a base64url P-256 SubjectPublicKeyInfo; throws on anything else. */
export function pointFromSpki(spki: string): Uint8Array {
  const der = fromB64url(spki);
  const head = Array.from(der.slice(0, 26), (b) => b.toString(16).padStart(2, '0')).join('');
  if (der.length !== 91 || head !== SPKI_P256 || der[26] !== 4) throw new ApprovalKeyError('failed', 'not a P-256 public key');
  return der.slice(26);
}

/** True only for a DER ECDSA SHA-256 signature of `payload` by the key in `spki`. */
export function verifyDeviceSignature(spki: string, payload: string, signature: unknown): boolean {
  if (typeof signature !== 'string' || signature.length === 0) return false;
  try {
    return p256.verify(fromB64url(signature), utf8ToBytes(payload), pointFromSpki(spki), { format: 'der', lowS: false });
  } catch {
    return false;
  }
}

/** What this phone remembers about its key on one hub (public data only; the private key stays in the Keystore). */
export interface ApprovalKeyRecord {
  hubUrl: string;
  keyId: string;
  publicKey: string;
  securityLevel: SecurityLevel;
}

const STORE = 'onemind.approvalkey.v1';

export async function loadRecord(hubUrl: string): Promise<ApprovalKeyRecord | null> {
  const raw = await loadSecret(STORE);
  if (!raw) return null;
  try {
    const r = JSON.parse(raw) as Partial<ApprovalKeyRecord>;
    if (r.hubUrl === hubUrl && typeof r.keyId === 'string' && typeof r.publicKey === 'string' && typeof r.securityLevel === 'string')
      return r as ApprovalKeyRecord;
  } catch {
    /* corrupt: treat as not enrolled */
  }
  return null;
}

/**
 * Register a new key with the hub (#702). The hub asks for a passkey sign-in on this session in the
 * last minutes; its refusal is passed through. Android reports where the key lives, unverified, so the
 * kind is `hardware-reported` (or `software`).
 */
export async function enrol(api: OneMindApi, hubUrl: string, label: string, native: ApprovalKeyNative | undefined = approvalKeyNative): Promise<ApprovalKeyRecord> {
  if (!native || !api.approverKeyRegister) throw new ApprovalKeyError('not_on_phone', 'this phone or hub has no approval keys');
  let made: Awaited<ReturnType<ApprovalKeyNative['create']>>;
  try {
    made = await native.create();
  } catch (e) {
    throw fromNative(e);
  }
  pointFromSpki(made.publicKey);
  try {
    const k = await api.approverKeyRegister({
      public_key: made.publicKey,
      label,
      key_kind: made.securityLevel === 'software' ? 'software' : 'hardware-reported',
    });
    const rec: ApprovalKeyRecord = { hubUrl, keyId: k.key_id, publicKey: made.publicKey, securityLevel: made.securityLevel };
    await saveSecret(STORE, JSON.stringify(rec));
    return rec;
  } catch (e) {
    native.remove();
    throw e;
  }
}

/** Revoke on the hub (best effort: an already-revoked key is fine), delete the key and forget it. */
export async function forget(api: OneMindApi, rec: ApprovalKeyRecord, native: ApprovalKeyNative | undefined = approvalKeyNative): Promise<void> {
  try {
    await api.approverKeyRevoke?.(rec.keyId);
  } catch (e) {
    if (!(e instanceof ApiError && e.code === 'not_found')) throw e;
  }
  native?.remove();
  await deleteSecret(STORE);
}

/** The approval-key half of approvals.ts' StepUp. */
export interface ApprovalSigner {
  sign(action: Action, opts: ApproveOptions, prompt: { title: string; subtitle: string }): Promise<DeviceSignature>;
}

// Challenges this app has signed since it started: a challenge is never signed twice.
const signedChallenges = new Set<string>();

export function makeSigner(rec: ApprovalKeyRecord, native: ApprovalKeyNative, signed: Set<string> = signedChallenges): ApprovalSigner {
  return {
    async sign(action, opts, prompt) {
      if (action.plan_sha256 && opts.plan_sha256 !== action.plan_sha256)
        throw new ApprovalKeyError('plan_changed', 'the plan changed since this card was loaded');
      const payload = signingPayload(opts.challenge, action.id, opts.action_sha256, opts.plan_sha256);
      if (opts.device_payload !== payload) throw new ApprovalKeyError('payload_mismatch', 'device_payload does not match this card');
      if (signed.has(opts.challenge)) throw new ApprovalKeyError('replay', 'challenge already signed');
      signed.add(opts.challenge);
      let signature: unknown;
      try {
        signature = await native.sign(payload, prompt.title, prompt.subtitle);
      } catch (e) {
        throw fromNative(e);
      }
      if (!verifyDeviceSignature(rec.publicKey, payload, signature)) throw new ApprovalKeyError('bad_signature', 'no valid signature');
      return { key_id: rec.keyId, challenge: opts.challenge, signature: signature as string };
    },
  };
}

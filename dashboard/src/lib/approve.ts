// SPDX-License-Identifier: Apache-2.0
// Approving, end to end (contract §12.4): ask the gateway for a challenge bound to this action and
// its plan, check the plan is the one the owner read, sign it with a passkey when the owner has one
// (or the gateway asks for one), then approve with the plan hash and, for an install, the sealed
// secrets form. The gateway decides; this only carries the proof. A passkey is never skipped
// silently: if signing is cancelled the approval does not happen.
import type { OneMindApi } from '../api/client';
import { ApiError, type Action, type ApproveBody } from '../api/types';
import { getPasskey, webauthnSupported } from './webauthn';

/** ApiError.reason when the gateway asked for a passkey and the browser did not produce one (none, cancelled, or no tap). */
export const PASSKEY_NOT_USED = 'passkey_not_used';

/** ApiError.reason when the gateway needs a passkey and this browser has no WebAuthn (an insecure page such as plain http, or an old browser). */
export const PASSKEY_UNAVAILABLE = 'passkey_unavailable';

export interface ApproveOpts {
  /** The owner has a passkey (GET /v1/me step_up.passkeys_active): sign every approval (F-2). */
  passkey?: boolean;
  /** The secrets form, already sealed in the browser (never a plain value). */
  sealed?: ApproveBody['sealed'];
  /** #173: the app id the owner typed to accept a licence that is not green (blocked or unknown). */
  acceptLicence?: string;
  /** Hold-to-approve: the measured hold, and the plan fingerprint the owner read (absent when the action has no plan). */
  hold?: { ms: number; plan?: string };
  /** Test seam; defaults to the browser's WebAuthn. */
  sign?: (publicKey: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

export async function approveWithStepUp(api: OneMindApi, action: Pick<Action, 'id' | 'plan_sha256'>, opts: ApproveOpts = {}): Promise<Action> {
  const extra: ApproveBody = { ...(opts.sealed ? { sealed: opts.sealed } : {}), ...(opts.acceptLicence ? { accept_licence: opts.acceptLicence } : {}),
    ...(opts.hold ? { hold_ms: opts.hold.ms } : {}) };
  // The hold is bound to the plan only when the action has one; many destructive actions have none.
  if (opts.hold && action.plan_sha256 && action.plan_sha256 !== opts.hold.plan)
    throw new ApiError(409, 'stale_precondition', 'Review the current plan before approving.', 'plan_changed');
  if (opts.hold && !api.approveOptions)
    throw new ApiError(400, 'unknown', 'Passkey approval is not available on this client.', 'approve_options_unavailable');
  if (!api.approveOptions) return api.approve(action.id, Object.keys(extra).length ? extra : undefined);
  const sign = opts.sign ?? getPasskey;
  const challenge = await api.approveOptions(action.id);
  // The plan on screen must be the plan the passkey signs. If it moved, the owner reads it again.
  if (action.plan_sha256 && challenge.plan_sha256 !== action.plan_sha256)
    throw new ApiError(409, 'stale_precondition', 'The plan changed since you opened this request. Review it again before approving.', 'plan_changed');
  const body: ApproveBody = { ...extra };
  if (challenge.plan_sha256) body.plan_sha256 = challenge.plan_sha256;
  const signed = async (): Promise<ApproveBody> => {
    try { return { ...body, webauthn: await sign(challenge.publicKey) }; }
    catch (e) {
      // Only a cancel, a timeout or no tap (the browser's NotAllowedError) is "not used": the owner can try again.
      // Anything else (wrong host for the RP ID, bad options, no WebAuthn) passes through with its own message.
      // Duck-typed: a DOMException is not always an `instanceof Error` across realms.
      // With no WebAuthn (plain http, old browser) there is no navigator.credentials and signing dies with a TypeError:
      // say that in words instead of showing the raw error.
      if (!opts.sign && !webauthnSupported())
        throw new ApiError(401, 'unauthenticated', 'This browser cannot use a passkey.', PASSKEY_UNAVAILABLE);
      const err = e as { name?: unknown; message?: unknown } | null;
      if (err && err.name === 'NotAllowedError') throw new ApiError(401, 'unauthenticated', typeof err.message === 'string' && err.message ? err.message : 'Your passkey was not used.', PASSKEY_NOT_USED);
      throw e;
    }
  };
  // A hold does not force a passkey: only physical actions need one, and the gateway answers those with
  // step_up_required (retried signed below). A destructive action on a box with no passkey goes unsigned.
  if (opts.passkey) return api.approve(action.id, await signed());
  try {
    return await api.approve(action.id, body);
  } catch (e) {
    // The gateway wants a passkey that the page did not expect to need (a destructive request).
    if (e instanceof ApiError && e.code === 'unauthenticated' && e.reason === 'step_up_required') {
      return api.approve(action.id, await signed());
    }
    throw e;
  }
}

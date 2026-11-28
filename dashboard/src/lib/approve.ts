// SPDX-License-Identifier: Apache-2.0
// Approving, end to end (contract §12.4): ask the gateway for a challenge bound to this action and
// its plan, check the plan is the one the owner read, sign it with a passkey when the owner has one
// (or the gateway asks for one), then approve with the plan hash and, for an install, the sealed
// secrets form. The gateway decides; this only carries the proof. A passkey is never skipped
// silently: if signing is cancelled the approval does not happen.
import type { OneMindApi } from '../api/client';
import { ApiError, type Action, type ApproveBody } from '../api/types';
import { getPasskey } from './webauthn';
import { askBoxCode } from './boxcode';

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
  /** Test seam; defaults to the dialog asking for the code the box's own screen shows (N-1 b). */
  boxCode?: (what: string) => Promise<string>;
}

/** The level a verification_level_unmet refusal names (D-028), L2 when it names none. */
export function levelOf(e: unknown): 'L2' | 'L3' | undefined {
  if (!(e instanceof ApiError) || e.reason !== 'verification_level_unmet') return undefined;
  return /\bL3\b/.test(e.message) ? 'L3' : 'L2';
}

/** approve-options' 409 verification_level_unmet in plain words: which key is missing and where to add it. */
export function plainLevelError(e: unknown): unknown {
  const level = levelOf(e);
  if (!level) return e;
  const what = level === 'L3' ? 'a biometric-only key (L3)' : 'your proven key (L2): a security key that proves its make and model';
  return new ApiError(409, 'conflict', `This approval needs ${what}. None of your sign-in keys is one yet. Add one under Settings > Security > Sign-in keys, then approve again.`, 'verification_level_unmet');
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
  let challenge: Awaited<ReturnType<NonNullable<OneMindApi['approveOptions']>>>;
  try { challenge = await api.approveOptions(action.id); } catch (e) { throw plainLevelError(e); }
  // The plan on screen must be the plan the passkey signs. If it moved, the owner reads it again.
  if (action.plan_sha256 && challenge.plan_sha256 !== action.plan_sha256)
    throw new ApiError(409, 'stale_precondition', 'The plan changed since you opened this request. Review it again before approving.', 'plan_changed');
  const body: ApproveBody = { ...extra };
  if (challenge.plan_sha256) body.plan_sha256 = challenge.plan_sha256;
  // D-028, N-1 b: before the first proven key, an L2 approval is a passkey plus the code the box's own
  // screen shows now. Asked before the passkey prompt, while the code is fresh.
  if (challenge.box_code_required) body.box_code = await (opts.boxCode ?? askBoxCode)(`approve ${action.id}`);
  const signed = async () => ({ ...body, webauthn: await sign(challenge.publicKey) });
  // A hold does not force a passkey: only physical actions need one, and the gateway answers those with
  // step_up_required (retried signed below). A destructive action on a box with no passkey goes unsigned.
  if (opts.passkey) return api.approve(action.id, await signed());
  try {
    return await api.approve(action.id, body);
  } catch (e) {
    // The gateway wants a passkey that the page did not expect to need (a destructive request).
    if (e instanceof ApiError && e.code === 'unauthenticated' && e.reason === 'step_up_required') return api.approve(action.id, await signed());
    throw e;
  }
}

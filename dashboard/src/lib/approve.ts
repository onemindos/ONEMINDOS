// SPDX-License-Identifier: Apache-2.0
// Approving, end to end (contract §12.4): ask the gateway for a challenge bound to this action and
// its plan, check the plan is the one the owner read, sign it with a passkey when the owner has one
// (or the gateway asks for one), then approve with the plan hash and, for an install, the sealed
// secrets form. The gateway decides; this only carries the proof. A passkey is never skipped
// silently: if signing is cancelled the approval does not happen.
import type { OneMindApi } from '../api/client';
import { ApiError, type Action, type ApproveBody } from '../api/types';
import { getPasskey } from './webauthn';

export interface ApproveOpts {
  /** The owner has a passkey (GET /v1/me step_up.passkeys_active): sign every approval (F-2). */
  passkey?: boolean;
  /** The secrets form, already sealed in the browser (never a plain value). */
  sealed?: ApproveBody['sealed'];
  /** Test seam; defaults to the browser's WebAuthn. */
  sign?: (publicKey: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

export async function approveWithStepUp(api: OneMindApi, action: Pick<Action, 'id' | 'plan_sha256'>, opts: ApproveOpts = {}): Promise<Action> {
  if (!api.approveOptions) return api.approve(action.id, opts.sealed ? { sealed: opts.sealed } : undefined);
  const sign = opts.sign ?? getPasskey;
  const challenge = await api.approveOptions(action.id);
  // The plan on screen must be the plan the passkey signs. If it moved, the owner reads it again.
  if (action.plan_sha256 && challenge.plan_sha256 !== action.plan_sha256)
    throw new ApiError(409, 'stale_precondition', 'The plan changed since you opened this request. Review it again before approving.', 'plan_changed');
  const body: ApproveBody = {};
  if (challenge.plan_sha256) body.plan_sha256 = challenge.plan_sha256;
  if (opts.sealed) body.sealed = opts.sealed;
  const signed = async () => ({ ...body, webauthn: await sign(challenge.publicKey) });
  if (opts.passkey) return api.approve(action.id, await signed());
  try {
    return await api.approve(action.id, body);
  } catch (e) {
    // The gateway wants a passkey that the page did not expect to need (a destructive request).
    if (e instanceof ApiError && e.code === 'unauthenticated' && e.reason === 'step_up_required') return api.approve(action.id, await signed());
    throw e;
  }
}

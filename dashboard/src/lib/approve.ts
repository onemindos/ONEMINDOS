// SPDX-License-Identifier: Apache-2.0
// Approving, end to end (contract §12.4): ask the gateway for a challenge bound to this action and
// its plan, check the plan is the one the owner read, and carry the requested proof and any
// sealed install inputs. The gateway decides which proof is sufficient (D-034).
import type { StepUpVerification } from '@onemind/sdk';
import type { ApproveOptions, OneMindApi } from '../api/client';
import { ApiError, type Action, type ApproveBody } from '../api/types';
import { getPasskey } from './webauthn';
import { askBoxCode } from './boxcode';
import { chooseVerification } from './verification';

export interface ApproveOpts {
  /** The owner has a passkey (GET /v1/me step_up.passkeys_active): sign every approval (F-2). */
  passkey?: boolean;
  /** A prior request has already shown this approval needs fresh proof. */
  forceProof?: boolean;
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
  verification?: StepUpVerification;
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

type ApprovalApi<Result> = Pick<OneMindApi, 'approveOptions'> & { approve(id: string, body?: ApproveBody): Promise<Result> };

type Rule = Pick<ApproveOptions, 'required_level' | 'box_available' | 'password_totp_available'>;

function approvalRule(error: unknown): Rule | undefined {
  if (!(error instanceof ApiError)) return undefined;
  for (const detail of error.details ?? []) {
    if (!detail || typeof detail !== 'object' || !('approval_verification' in detail)) continue;
    const rule = detail.approval_verification;
    if (!rule || typeof rule !== 'object' || !('required_level' in rule) || typeof rule.required_level !== 'string') continue;
    if (!['L0', 'L1', 'L2', 'L3'].includes(rule.required_level)) continue;
    return {
      required_level: rule.required_level as Rule['required_level'],
      box_available: 'box_available' in rule && rule.box_available === true,
      password_totp_available: 'password_totp_available' in rule && rule.password_totp_available === true,
    };
  }
}

export async function approveWithStepUp<Result>(api: ApprovalApi<Result>, action: Pick<Action, 'id' | 'plan_sha256'>, opts: ApproveOpts = {}): Promise<Result> {
  const extra: ApproveBody = { ...(opts.sealed ? { sealed: opts.sealed } : {}), ...(opts.acceptLicence ? { accept_licence: opts.acceptLicence } : {}),
    ...(opts.hold ? { hold_ms: opts.hold.ms } : {}) };
  // The hold is bound to the plan only when the action has one; many destructive actions have none.
  if (opts.hold && action.plan_sha256 && action.plan_sha256 !== opts.hold.plan)
    throw new ApiError(409, 'stale_precondition', 'Review the current plan before approving.', 'plan_changed');
  if (opts.hold && !api.approveOptions)
    throw new ApiError(400, 'unknown', 'Passkey approval is not available on this client.', 'approve_options_unavailable');
  if (!api.approveOptions) return api.approve(action.id, Object.keys(extra).length ? extra : undefined);
  const options = api.approveOptions.bind(api);
  const checkedBody = (challenge: ApproveOptions): ApproveBody => {
    if (action.plan_sha256 && challenge.plan_sha256 !== action.plan_sha256) {
      throw new ApiError(409, 'stale_precondition', 'The plan changed since you opened this request. Review it again before approving.', 'plan_changed');
    }
    return { ...extra, ...(challenge.plan_sha256 ? { plan_sha256: challenge.plan_sha256 } : {}) };
  };
  const proof = async (rule: Rule, initial?: ApproveOptions, refusal?: unknown) => {
    const request = { op: `approve ${action.id}`, target: action.id, body: extra,
      required_level: rule.required_level ?? 'L1', box: rule.box_available ? 'alt' as const : null };
    const selected = opts.verification ? await opts.verification(request)
      : rule.password_totp_available || rule.box_available ? await chooseVerification(request, !!rule.password_totp_available)
        : { method: 'passkey' as const };
    if (!initial && selected.method === 'passkey' && !selected.atBox) throw plainLevelError(refusal);
    const challenge = selected.method === 'password+totp' || selected.atBox || !initial
      ? await options(action.id, { method: selected.method, ...(selected.atBox ? { at_box: true } : {}) }) : initial;
    const body = checkedBody(challenge);
    if (challenge.box_code_required) body.box_code = await (opts.boxCode ?? askBoxCode)(`approve ${action.id}`);
    if (selected.method === 'password+totp') body.password_totp = { challenge: challenge.challenge, password: selected.password, totp: selected.totp };
    else body.webauthn = await (opts.sign ?? getPasskey)(challenge.publicKey);
    return api.approve(action.id, body);
  };
  let challenge: ApproveOptions;
  try { challenge = await options(action.id); }
  catch (error) {
    const rule = approvalRule(error);
    if (rule && (rule.password_totp_available || rule.box_available)) return proof(rule, undefined, error);
    throw plainLevelError(error);
  }
  const body = checkedBody(challenge);
  if (opts.forceProof || (opts.passkey && challenge.password_totp_available === undefined) || challenge.box_code_required) return proof(challenge, challenge);
  try {
    return await api.approve(action.id, body);
  } catch (e) {
    if (e instanceof ApiError && e.code === 'unauthenticated' && e.reason === 'step_up_required') return proof(approvalRule(e) ?? challenge, challenge);
    throw e;
  }
}

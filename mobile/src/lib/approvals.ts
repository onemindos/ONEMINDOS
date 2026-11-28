// SPDX-License-Identifier: Apache-2.0
// The approval flow (contract §3): request an action, then an owner approves or
// denies it. The gateway is the authority; these helpers only turn its answers
// into what the screens say, and never decide anything on the phone.
import { Features, OP, type OneMindApi } from '../api/client';
import { ApiError, type Action, type ActionType, type ApproveBody, type PrincipalRef, type Risk, type SealedInput } from '../api/types';
import { ApprovalKeyError, approvalKeyMessage, type ApprovalSigner } from '../approvalKey';
import { uuidv4 } from './uuid';
import { PasskeyError, passkeyMessage, requestOptionsFrom, rpIdFor, type Passkeys } from './webauthn';

/** Default approval window for actions created from the phone (same as MCP request_action, §11.3). */
export const REQUEST_TTL_MS = 24 * 3600_000;

const VERB: Record<string, string> = {
  'app.install': 'Install',
  'app.remove': 'Remove',
  'app.start': 'Start',
  'app.stop': 'Stop',
  'app.restart': 'Restart',
  'app.update': 'Update',
};

export function actionTitle(a: Pick<Action, 'type' | 'params'>): string {
  const verb = VERB[a.type];
  const subject = a.params?.app_id ?? a.params?.node_id ?? a.params?.snapshot_id;
  if (verb) return `${verb} ${a.params?.app_id ?? '(no app)'}`;
  return typeof subject === 'string' ? `${a.type} ${subject}` : a.type;
}

/** §12.3 risk classes in plain words, for the approval card. */
export const RISK_LABEL: Record<Risk, string> = {
  read: 'Read only',
  write: 'Reversible change',
  sensitive: 'Sensitive: widens what runs or who can reach it',
  destructive: 'Destructive: data loss or downtime possible',
  actuate: 'Moves or switches a physical device',
};

/** §12.3: destructive and actuate always need a passkey; once the owner has one, every approval does (F-2). */
export function needsPasskey(a: Pick<Action, 'risk'>, ownerHasPasskey: boolean): boolean {
  return ownerHasPasskey || a.risk === 'destructive' || a.risk === 'actuate';
}

/**
 * Whether the hub takes this phone's approval key for the action under its default policy (#838, F-2):
 * read, write and sensitive only. Destructive and actuate fall back to the passkey (which also takes
 * the screen lock) unless the hub turns on `approver_key_high_risk`; physical actions always do.
 */
export function keyCovers(a: Pick<Action, 'risk'>): boolean {
  return a.risk === 'read' || a.risk === 'write' || a.risk === 'sensitive';
}

/** "agent ops-agent" / "person owner" / "unknown requester". */
export function principalLabel(p: PrincipalRef | null | undefined): string {
  if (!p) return 'unknown requester';
  return `${p.kind} ${p.id}`;
}

export function isPending(a: Action): boolean {
  return a.state === 'awaiting_approval';
}

/** Newest first by updated_at, then created_at; actions without times go last. */
export function sortByRecent(list: Action[]): Action[] {
  const t = (a: Action) => Date.parse(a.updated_at ?? a.created_at ?? '') || 0;
  return [...list].sort((x, y) => t(y) - t(x));
}

/** Create an install/remove request. The same `idempotencyKey` returns the same action (§3). */
export async function requestAction(
  api: OneMindApi,
  type: ActionType,
  appId: string,
  opts: { now?: number; idempotencyKey?: string } = {},
): Promise<Action> {
  const now = opts.now ?? Date.now();
  return api.createAction({
    type,
    params: { app_id: appId },
    idempotency_key: opts.idempotencyKey ?? uuidv4(),
    expires_at: new Date(now + REQUEST_TTL_MS).toISOString(),
  });
}

export type Decision = 'approve' | 'deny';

export type DecideResult =
  | { ok: true; action: Action; message: string }
  | { ok: false; message: string; forbidden: boolean; code: ApiError['code'] | 'passkey' | 'approval_key'; reason?: string };

/** What the approval needs besides the action: what the hub serves and how this phone signs. */
export interface StepUp {
  features: Features;
  /** The platform authenticator; undefined in the demo or when the native module is missing. */
  passkeys?: Passkeys;
  /** `/v1/me` passkeys > 0 (F-2: then every approval carries a passkey). */
  ownerHasPasskey: boolean;
  hubUrl?: string;
  /** This phone's enrolled approval key (#703); when set, every approval is signed inside the biometric prompt. */
  approvalKey?: ApprovalSigner;
  /** Deny reason (optional, shown to the requester, §12.4). */
  reason?: string;
  /** #528: the install's secrets form, already sealed on this phone. Sent with every approve attempt. */
  sealed?: SealedInput;
}

const NO_STEP_UP: StepUp = { features: Features.none(), ownerHasPasskey: false };

async function sign(a: Action, ctx: StepUp, opts: Awaited<ReturnType<OneMindApi['approveOptions']>>) {
  if (!ctx.passkeys || !ctx.passkeys.supported())
    throw new PasskeyError('not_supported', 'no platform authenticator');
  return ctx.passkeys.get(requestOptionsFrom(opts, rpIdFor(ctx.hubUrl)));
}

/**
 * §12.4 approval: fetch a challenge bound to the action and its plan, check the plan is the one on
 * the card, sign with a passkey when the risk or the owner's setup needs it, and send both.
 * If the hub asks for a passkey that the phone did not expect to need, sign once and retry.
 */
async function approveBound(api: OneMindApi, a: Action, ctx: StepUp): Promise<{ action: Action; usedKey: boolean }> {
  let usedKey = false;
  // The approval key whenever the hub offers device signing (`device_payload`); otherwise a passkey
  // only when one is needed ('key-or-passkey'), never just because this phone has a key ('key-or-none').
  type Step = 'none' | 'key-or-none' | 'key-or-passkey' | 'passkey';
  const once = async (step: Step) => {
    const opts = await api.approveOptions(a.id);
    if (a.plan_sha256 && opts.plan_sha256 !== a.plan_sha256)
      throw new ApiError(409, 'stale_precondition', 'the plan changed since this card was loaded', { reason: 'plan_changed' });
    const body: ApproveBody = { ...(opts.plan_sha256 ? { plan_sha256: opts.plan_sha256 } : {}), ...(ctx.sealed ? { sealed: ctx.sealed } : {}) };
    usedKey = (step === 'key-or-none' || step === 'key-or-passkey') && !!ctx.approvalKey && !!opts.device_payload;
    if (usedKey) body.device_signature = await ctx.approvalKey!.sign(a, opts, keyPrompt(a, opts));
    else if (step === 'key-or-passkey' || step === 'passkey') body.webauthn = await sign(a, ctx, opts);
    return api.approve(a.id, body);
  };
  const first: Step = needsPasskey(a, ctx.ownerHasPasskey) ? 'key-or-passkey' : ctx.approvalKey ? 'key-or-none' : 'none';
  try {
    return { action: await once(first), usedKey };
  } catch (e) {
    const stepUp = e instanceof ApiError && e.code === 'unauthenticated' && e.reason === 'step_up_required';
    // The key was refused (F-2: destructive and actuate need a passkey): use the passkey.
    // No step-up was sent yet: add one, the key if the hub takes it, else a passkey.
    if (stepUp && usedKey) return { action: await once('passkey'), usedKey: false };
    if (stepUp && first !== 'key-or-passkey') return { action: await once('key-or-passkey'), usedKey };
    throw e;
  }
}

/** What the system biometric prompt says: the action and the plan the signature is bound to. */
function keyPrompt(a: Action, opts: { plan_sha256: string | null }): { title: string; subtitle: string } {
  const plan = opts.plan_sha256 ? `Plan ${opts.plan_sha256.replace(/^sha256:/, '').slice(0, 12)}` : 'No plan';
  return { title: `Approve: ${actionTitle(a)}`, subtitle: a.risk ? `${plan} · ${RISK_LABEL[a.risk]}` : plan };
}

/** v0 approval (no approve-options). A §12 hub that wants the plan hash says `plan_unchecked`; then send it. */
async function approvePlain(api: OneMindApi, a: Action, ctx: StepUp): Promise<Action> {
  try {
    return await api.approve(a.id, ctx.sealed ? { sealed: ctx.sealed } : undefined);
  } catch (e) {
    if (e instanceof ApiError && e.reason === 'plan_unchecked' && ctx.features.has(OP.preview)) {
      const p = await api.preview(a.id);
      if (a.plan_sha256 && p.plan_sha256 !== a.plan_sha256)
        throw new ApiError(409, 'stale_precondition', 'the plan changed since this card was loaded', { reason: 'plan_changed' });
      return api.approve(a.id, { plan_sha256: p.plan_sha256, ...(ctx.sealed ? { sealed: ctx.sealed } : {}) });
    }
    throw e;
  }
}

/** Approve or deny one action and say what happened in plain words. Deny never needs a passkey. */
export async function decide(api: OneMindApi, action: Action, decision: Decision, ctx: StepUp = NO_STEP_UP): Promise<DecideResult> {
  const title = actionTitle(action);
  try {
    let usedKey = false;
    let updated: Action;
    if (decision === 'deny') updated = await api.deny(action.id, ctx.reason);
    else if (ctx.features.has(OP.approveOptions)) ({ action: updated, usedKey } = await approveBound(api, action, ctx));
    else updated = await approvePlain(api, action, ctx);
    const how = usedKey
      ? " with this phone's approval key"
      : updated.approval === 'passkey'
        ? ' with your passkey'
        : updated.approval === 'token'
          ? ' (without a passkey)'
          : '';
    const message =
      decision === 'deny'
        ? `Denied: ${title}.`
        : updated.state === 'succeeded'
          ? `Approved${how} and done: ${title}.`
          : updated.state === 'failed'
            ? `Approved${how}, but it failed: ${updated.result?.message ?? 'no details from the hub'}.`
            : `Approved${how}: ${title} (${updated.state.replace(/_/g, ' ')}).`;
    return { ok: true, action: updated, message };
  } catch (e) {
    if (e instanceof ApprovalKeyError)
      return { ok: false, message: approvalKeyMessage(e), forbidden: false, code: 'approval_key', reason: e.kind };
    if (e instanceof PasskeyError)
      return { ok: false, message: passkeyMessage(e, rpIdFor(ctx.hubUrl)), forbidden: false, code: 'passkey', reason: e.kind };
    const err = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
    const fail = (message: string) => ({ ok: false as const, message, forbidden: err.code === 'permission_denied', code: err.code, reason: err.reason });
    if (err.reason === 'plan_changed') return fail(`${title} changed since you opened it. Nothing was approved; check the new version.`);
    if (err.reason === 'licence_unconfirmed') return fail(`${title} has a licence that needs you to read and accept it by typing the app id. Nothing was approved; do that on the dashboard or with the onemind command.`);
    if (err.reason === 'step_up_required') return fail('The hub needs your passkey for this, and this phone could not give one. Approve on the dashboard.');
    switch (err.code) {
      case 'policy_refused':
        return fail(`The install sandbox refused this plan: ${err.message}`);
      case 'rate_limited':
        return fail(`The hub asks to slow down${err.retryAfterS ? `; try again in ${err.retryAfterS} s` : ''}.`);
      case 'unavailable':
        return fail(`The hub cannot do this right now: ${err.message}. Nothing was changed.`);
      case 'permission_denied':
        return fail('Only an owner can approve or deny. This token is not an owner.');
      case 'expired':
        return fail(`${title} expired before it was approved. Ask again if it is still needed.`);
      case 'stale_precondition':
        return fail(`The hub refused: ${err.message}`);
      case 'conflict':
        return fail(`${title} was already decided elsewhere. The list is refreshed.`);
      case 'not_found':
        return fail(`${title} no longer exists on the hub.`);
      case 'network':
        return fail(`Could not reach the hub: ${err.message}. Nothing was changed.`);
      default:
        return fail(`Could not ${decision}: ${err.message}`);
    }
  }
}

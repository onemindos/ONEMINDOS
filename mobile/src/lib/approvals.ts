// SPDX-License-Identifier: Apache-2.0
// The approval flow (contract §3): request an action, then an owner approves or
// denies it. The gateway is the authority; these helpers only turn its answers
// into what the screens say, and never decide anything on the phone.
import type { OneMindApi } from '../api/client';
import { ApiError, type Action, type ActionType, type PrincipalRef } from '../api/types';
import { uuidv4 } from './uuid';

/** Default approval window for actions created from the phone (same as MCP request_action, §11.3). */
export const REQUEST_TTL_MS = 24 * 3600_000;

const VERB: Record<string, string> = { 'app.install': 'Install', 'app.remove': 'Remove' };

export function actionTitle(a: Pick<Action, 'type' | 'params'>): string {
  return `${VERB[a.type] ?? a.type} ${a.params?.app_id ?? '(no app)'}`;
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
  | { ok: false; message: string; forbidden: boolean; code: ApiError['code'] };

/** Approve or deny one action and say what happened in plain words. */
export async function decide(api: OneMindApi, action: Action, decision: Decision): Promise<DecideResult> {
  const title = actionTitle(action);
  try {
    const updated = decision === 'approve' ? await api.approve(action.id) : await api.deny(action.id);
    const message =
      decision === 'deny'
        ? `Denied: ${title}.`
        : updated.state === 'succeeded'
          ? `Approved and done: ${title}.`
          : updated.state === 'failed'
            ? `Approved, but it failed: ${updated.result?.message ?? 'no details from the hub'}.`
            : `Approved: ${title} (${updated.state.replace(/_/g, ' ')}).`;
    return { ok: true, action: updated, message };
  } catch (e) {
    const err = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
    const fail = (message: string) => ({ ok: false as const, message, forbidden: err.code === 'permission_denied', code: err.code });
    switch (err.code) {
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

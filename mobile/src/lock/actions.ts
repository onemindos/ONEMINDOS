// SPDX-License-Identifier: Apache-2.0
// Lock-screen buttons on an approval notification (issue #704): Review and Deny, both requiring the
// phone to be unlocked. Approve is never a notification button: approving needs the approval card
// and, where the box asks for it, the passkey signature (lib/approvals). A plain tap only opens the app.
import type { OneMindApi } from '../api/client';

export const APPROVAL_CATEGORY = 'approval';
export const ACTION_REVIEW = 'review';
export const ACTION_DENY = 'deny';

const ID = /^[A-Za-z0-9_-]{1,64}$/;

/** What a Deny points at: the action itself, or (closed-app Android ping) the notification about it. */
export type DenyTarget = { actionId: string } | { notificationId: string };

export type DenyOutcome = 'denied' | 'cancelled' | 'nothing_to_deny' | 'failed';

/** A notification response, reduced to what decides what happens. */
export interface ResponseLike {
  actionIdentifier: string;
  notification: { request: { identifier: string; content: { data?: Record<string, unknown> | null } } };
}

export type Intent = { kind: 'deny'; target: DenyTarget } | { kind: 'open'; data: Record<string, unknown> | undefined };

/** Deny button → deny (after unlock); Review button or a plain tap → open the app there. Nothing approves. */
export function responseIntent(r: ResponseLike): Intent {
  const data = r.notification.request.content.data ?? undefined;
  const actionId = data?.action_id;
  if (r.actionIdentifier === ACTION_DENY && typeof actionId === 'string' && ID.test(actionId)) return { kind: 'deny', target: { actionId } };
  if (r.actionIdentifier === ACTION_REVIEW) return { kind: 'open', data: { ...data, route: 'approvals' } };
  return { kind: 'open', data };
}

/**
 * Deny links from the closed-app Android notification (modules/onemind-unifiedpush):
 * `onemind://approvals?deny=<action id>` or `onemind://approvals?deny_notification=<notification id>`.
 * Any app can open a link, so a link alone never denies: the person still unlocks first.
 */
export function parseDenyLink(url: string | null | undefined): DenyTarget | undefined {
  if (!url) return undefined;
  const m = /^onemind:\/\/approvals\?(.*)$/.exec(url);
  if (!m) return undefined;
  const q = new URLSearchParams(m[1]);
  const a = q.get('deny');
  if (a && ID.test(a)) return { actionId: a };
  const n = q.get('deny_notification');
  if (n && ID.test(n)) return { notificationId: n };
  return undefined;
}

/**
 * Record a deny, but only after the person unlocks (`confirm`). Cancelling the prompt changes nothing
 * on the box. The box stays the authority: a deny of an action that is no longer waiting just fails.
 */
export async function denyAfterUnlock(
  api: Pick<OneMindApi, 'deny' | 'notification'>,
  target: DenyTarget,
  confirm: (reason: string) => Promise<boolean>,
): Promise<{ outcome: DenyOutcome; message: string }> {
  let actionId: string | undefined;
  if ('actionId' in target) actionId = target.actionId;
  else {
    try {
      actionId = (await api.notification(target.notificationId)).action_id ?? undefined;
    } catch {
      return { outcome: 'failed', message: 'Could not reach your box to find that request.' };
    }
  }
  if (!actionId) return { outcome: 'nothing_to_deny', message: 'That notification is not a request waiting for approval.' };
  if (!(await confirm('Unlock to deny this request'))) return { outcome: 'cancelled', message: 'Not denied: unlock was cancelled.' };
  try {
    await api.deny(actionId);
    return { outcome: 'denied', message: 'Denied. The request will not run.' };
  } catch (e) {
    return { outcome: 'failed', message: `Not denied: ${e instanceof Error ? e.message : 'the box refused'}` };
  }
}

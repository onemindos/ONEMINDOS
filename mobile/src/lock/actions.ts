// SPDX-License-Identifier: Apache-2.0
// Lock-screen buttons on an approval notification (issue #704): Review and Deny, both requiring the
// phone to be unlocked. Approve is never a notification button: approving needs the approval card
// and, where the box asks for it, the passkey signature (lib/approvals). A plain tap only opens the app.
import type { OneMindApi } from '../api/client';
import { approvalActionId } from '../lib/alerts';
import { actionTitle, isPending } from '../lib/approvals';

export const APPROVAL_CATEGORY = 'approval';
export const ACTION_REVIEW = 'review';
export const ACTION_DENY = 'deny';

export function isRequestId(id: unknown): id is string {
  return typeof id === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(id);
}

/** What Review or Deny points at: the action itself, or (closed-app Android ping) the notification about it. */
export type ApprovalTarget = { actionId: string } | { notificationId: string };

export type DenyOutcome = 'denied' | 'cancelled' | 'nothing_to_deny' | 'failed';

/** A notification response, reduced to what decides what happens. */
export interface ResponseLike {
  actionIdentifier: string;
  notification: { request: { identifier: string; content: { data?: Record<string, unknown> | null } } };
}

export type Intent = { kind: 'deny'; target: ApprovalTarget } | { kind: 'open'; data: Record<string, unknown> | undefined };

/** Deny button → deny (after unlock); Review button or a plain tap → open the app there. Nothing approves. */
export function responseIntent(r: ResponseLike): Intent {
  const data = r.notification.request.content.data ?? undefined;
  const actionId = data?.action_id;
  if (r.actionIdentifier === ACTION_DENY && isRequestId(actionId)) return { kind: 'deny', target: { actionId } };
  if (r.actionIdentifier === ACTION_REVIEW) return { kind: 'open', data: { ...data, route: 'approvals' } };
  return { kind: 'open', data };
}

function approvalLinkQuery(url: string | null | undefined): URLSearchParams | undefined {
  const match = url && /^onemind:\/\/approvals\?(.*)$/.exec(url);
  const query = match && match[1];
  if (query === null || query === undefined) return undefined;
  try {
    // React Native's query parser throws on bad escapes. Reject the entire malformed link.
    decodeURI(query);
    return new URLSearchParams(query);
  } catch {
    return undefined;
  }
}

/** The notification listener owns Review URLs, including when navigation is still starting. */
export function allowNavigationLink(url: string): boolean {
  if (!url.startsWith('onemind://approvals?')) return true;
  const query = approvalLinkQuery(url);
  return !!query && !query.has('review') && !query.has('review_notification');
}

function parseApprovalLink(url: string | null | undefined, action: 'deny' | 'review'): ApprovalTarget | undefined {
  const query = approvalLinkQuery(url);
  const actionId = query?.get(action);
  if (isRequestId(actionId)) return { actionId };
  const notificationId = query?.get(`${action}_notification`);
  if (isRequestId(notificationId)) return { notificationId };
  return undefined;
}

/** Any app can open a link. A Deny still requires confirmation for its resolved request. */
export function parseDenyLink(url: string | null | undefined): ApprovalTarget | undefined {
  return parseApprovalLink(url, 'deny');
}

export function parseReviewLink(url: string | null | undefined): ApprovalTarget | undefined {
  return parseApprovalLink(url, 'review');
}

export async function resolveApprovalTarget(api: Pick<OneMindApi, 'notification'>, target: ApprovalTarget): Promise<string | undefined> {
  if ('actionId' in target) return target.actionId;
  const id = approvalActionId(await api.notification(target.notificationId));
  return isRequestId(id) ? id : undefined;
}

type DenyResult = { outcome: DenyOutcome; message: string };
type DenyApi = Pick<OneMindApi, 'deny' | 'notification' | 'action' | 'hubOffsetMs'>;
const denials = new WeakMap<DenyApi, Map<string, Promise<DenyResult>>>();

const noRequest: DenyResult = {
  outcome: 'nothing_to_deny',
  message: 'That notification is not a request waiting for approval.',
};
const lookupFailed: DenyResult = {
  outcome: 'failed',
  message: 'Could not reach your box to find that request.',
};

/** Coalesce simultaneous deliveries for the same request on the same hub client. */
export async function denyAfterUnlock(
  api: DenyApi,
  target: ApprovalTarget,
  confirm: (reason: string, requestId: string) => Promise<boolean>,
): Promise<DenyResult> {
  let actionId: string | undefined;
  try {
    actionId = await resolveApprovalTarget(api, target);
  } catch {
    return lookupFailed;
  }
  if (!actionId) return noRequest;
  let pending = denials.get(api);
  if (!pending) {
    pending = new Map();
    denials.set(api, pending);
  }
  const existing = pending.get(actionId);
  if (existing) return existing;
  const attempt = denyRequest(api, actionId, confirm);
  pending.set(actionId, attempt);
  try {
    return await attempt;
  } finally {
    pending.delete(actionId);
  }
}

async function denyRequest(api: DenyApi, actionId: string, confirm: (reason: string, requestId: string) => Promise<boolean>): Promise<DenyResult> {
  let action;
  try {
    action = await api.action(actionId);
  } catch {
    return lookupFailed;
  }
  if (!isPending(action) || !(Date.parse(action.expires_at) > Date.now() + (api.hubOffsetMs() ?? 0))) return noRequest;
  const title = actionTitle(action);
  const shortTitle = title.length > 80 ? `${title.slice(0, 79)}…` : title;
  if (!(await confirm(`Unlock to deny: ${shortTitle}`, actionId))) {
    return { outcome: 'cancelled', message: 'Not denied: unlock was cancelled.' };
  }
  try {
    await api.deny(actionId);
    return { outcome: 'denied', message: 'Denied. The request will not run.' };
  } catch (e) {
    return { outcome: 'failed', message: `Not denied: ${e instanceof Error ? e.message : 'the box refused'}` };
  }
}

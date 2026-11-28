// SPDX-License-Identifier: Apache-2.0
// Which actions are app requests, and the words the Market uses for them. Read from the hub's
// action list only; nothing here files or decides anything.
import type { Action } from '../../api/types';
import { appIdOf } from '../../data/adapters';

const VERB: Record<string, string> = {
  'app.install': 'Install',
  'app.update': 'Update',
  'app.remove': 'Remove',
  'app.start': 'Start',
  'app.stop': 'Stop',
  'app.restart': 'Restart',
};

/** An app.* action that names an app (the §3 types; anything else is not a Market request). */
export function isAppRequest(a: Pick<Action, 'type' | 'params'>): boolean {
  return a.type in VERB && appIdOf(a) !== undefined;
}

export function requestVerb(a: Pick<Action, 'type'>): string {
  return VERB[a.type] ?? a.type;
}

/** Who is looking: `account` from GET /v1/me on a real box (the session's `principal` is only known in demo and tests). */
export type Viewer = { id: string; kind: string } | undefined;

/** The person who filed it is the person looking: the hub records a requester cancelling as "cancelled". */
export function ownsRequest(a: Pick<Action, 'requested_by'>, me: Viewer): boolean {
  return !!me && me.kind === 'person' && a.requested_by?.kind === 'person' && a.requested_by.id === me.id;
}

/** "you", or the id the hub sent; never a guessed name. */
export function askedBy(a: Pick<Action, 'requested_by'>, me: Viewer): string {
  if (ownsRequest(a, me)) return 'you';
  return a.requested_by ? `${a.requested_by.id}${a.requested_by.kind === 'agent' ? ' (agent)' : ''}` : 'not reported';
}

/** Waiting first, then the newest. */
export function sortRequests(list: Action[]): Action[] {
  const t = (a: Action) => Date.parse(a.updated_at ?? a.created_at ?? '') || 0;
  return [...list].sort((a, b) => Number(b.state === 'awaiting_approval') - Number(a.state === 'awaiting_approval') || t(b) - t(a));
}

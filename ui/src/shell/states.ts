// SPDX-License-Identifier: Apache-2.0
// One rule for what a panel shows (docs/design/IA.md §4 "Screen states checklist"):
// loading, empty, error, stale, offline, forbidden or ready. Every shell component, and any
// screen that wants the same behaviour, resolves its state here so the rules stay identical.
import { NODE_LIMITS, type FreshnessLimits } from '../lib/freshness';
import { secondsSince } from '../lib/time';
import type { ShellIconName } from './icons';

/** Contract §3 error codes. */
export type GatewayErrorCode =
  | 'permission_denied'
  | 'stale_precondition'
  | 'expired'
  | 'conflict'
  | 'outcome_unknown'
  | 'not_found'
  | 'unauthenticated'
  | 'unreachable';

export interface GatewayError {
  error: GatewayErrorCode;
  message: string;
}

export interface Resource<T> {
  data?: T;
  loading?: boolean;
  error?: GatewayError;
  /** When the hub last confirmed this data (RFC 3339). */
  observedAt?: string;
}

export type ViewState = 'loading' | 'empty' | 'error' | 'stale' | 'offline' | 'forbidden' | 'ready';

export interface ViewStateOptions<T> {
  now: number;
  isEmpty?: (data: T) => boolean;
  limits?: FreshnessLimits;
}

const defaultEmpty = (d: unknown) => (Array.isArray(d) ? d.length === 0 : d == null);

/**
 * Resolve the state. Order matters:
 * forbidden beats everything (never hide a control silently); data we already hold is never
 * thrown away on an error, it is shown as stale or offline instead (P2: no cached green).
 */
export function viewState<T>(r: Resource<T>, { now, isEmpty = defaultEmpty, limits = NODE_LIMITS }: ViewStateOptions<T>): ViewState {
  if (r.error?.error === 'permission_denied') return 'forbidden';
  const has = r.data !== undefined;
  if (!has) {
    if (r.error) return 'error';
    return r.loading ? 'loading' : 'empty';
  }
  const age = r.observedAt ? secondsSince(r.observedAt, now) : 0;
  if (r.error || age > limits.staleAfter) {
    if (r.error?.error === 'unreachable' || age > limits.offlineAfter) return 'offline';
    return 'stale';
  }
  return isEmpty(r.data as T) ? 'empty' : 'ready';
}

/** After 10 s a loading state must say what is slow (IA §4). */
export const SLOW_AFTER_S = 10;
export function isSlow(startedAt: number, now: number): boolean {
  return now - startedAt >= SLOW_AFTER_S * 1000;
}

export interface EmptyPreset {
  icon: ShellIconName;
  title: string;
  body: string;
  /** The CLI or API line that does the same (P4). "planned" verbs are labelled by the caller. */
  command?: string;
}

/**
 * Copy for every empty list in the dashboard. Each one says why it is empty and what happens
 * next, never a bare "No data" (IA §4). Keys are screen ids from IA.md.
 */
export const EMPTY_PRESETS = {
  approvals: {
    icon: 'approvals',
    title: 'Nothing is waiting for you',
    body: 'When a person, an agent or the system asks for a change, it waits here until you approve or deny it.',
    command: 'GET /v1/actions?state=awaiting_approval',
  },
  notifications: {
    icon: 'inbox',
    title: 'You are all caught up',
    body: 'Approvals, failed backups, offline nodes and rollbacks land here first.',
    command: 'onemind alerts list',
  },
  'notifications-unread': {
    icon: 'check',
    title: 'Nothing unread',
    body: 'Everything here has been read. Older notifications are still under All.',
  },
  'notifications-needs-you': {
    icon: 'approvals',
    title: 'Nothing needs you',
    body: 'No request is waiting and no alert is critical.',
  },
  'apps-installed': {
    icon: 'apps',
    title: 'No apps yet',
    body: 'Pick one from the Market. Installing is a request: you approve it, then it starts.',
    command: 'onemind apps list --installed',
  },
  nodes: {
    icon: 'nodes',
    title: 'Only the hub so far',
    body: 'Add another machine to run more apps or keep a backup copy. It joins with a one-time code.',
    command: 'onemind node join',
  },
  activity: {
    icon: 'activity',
    title: 'No activity in this range',
    body: 'Every request, approval and run is recorded in the audit log. Widen the filters to see more.',
    command: 'GET /v1/audit',
  },
  backups: {
    icon: 'backups',
    title: 'No backup has run yet',
    body: 'Choose where backups go. Nothing is protected until the first backup and a test restore have run.',
    command: 'onemind backup run',
  },
  search: {
    icon: 'search',
    title: 'No matches',
    body: 'Try a shorter word, an app category, or type > to search requests you can make.',
  },
} satisfies Record<string, EmptyPreset>;
export type EmptyPresetId = keyof typeof EMPTY_PRESETS;

/** Plain-language lead for each error code; the hub's own message is shown under it. */
export const ERROR_COPY: Record<GatewayErrorCode, string> = {
  permission_denied: 'You do not have permission to see this.',
  stale_precondition: 'Something changed while you were looking. Reload to see the current state.',
  expired: 'This request expired before it was decided.',
  conflict: 'Another change is already running for this.',
  outcome_unknown: 'The hub could not confirm what happened.',
  not_found: 'This no longer exists.',
  unauthenticated: 'Your session ended. Sign in again.',
  unreachable: 'The hub is not answering.',
};

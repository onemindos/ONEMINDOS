// SPDX-License-Identifier: Apache-2.0
// Copied from dashboard/src/lib/time.ts (feat/gwmcp, commit 951470f) so the phone app and the
// dashboard speak the same contract types. Keep the two in sync; mobile changes noted inline.
import type { NodeStatus } from '../api/types';

/** Contract §3: stale after 30 s, offline after 120 s without a heartbeat. */
export const STALE_AFTER_S = 30;
export const OFFLINE_AFTER_S = 120;

export function secondsSince(iso: string, now: number): number | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((now - t) / 1000));
}

/** "12s ago", "4m ago", "3h ago", "2d ago". */
export function formatAgo(seconds: number | null): string {
  if (seconds === null) return 'unknown';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function formatIn(iso: string, now: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'unknown';
  const s = Math.floor((t - now) / 1000);
  if (s <= 0) return 'expired';
  if (s < 60) return `in ${s}s`;
  if (s < 3600) return `in ${Math.floor(s / 60)}m`;
  if (s < 86400) return `in ${Math.floor(s / 3600)}h`;
  return `in ${Math.floor(s / 86400)}d`;
}

const RANK: Record<NodeStatus, number> = { online: 0, stale: 1, offline: 2 };

function fromAge(ageS: number): NodeStatus {
  return ageS >= OFFLINE_AFTER_S ? 'offline' : ageS >= STALE_AFTER_S ? 'stale' : 'online';
}

function worse(a: NodeStatus, b: NodeStatus): NodeStatus {
  return RANK[a] >= RANK[b] ? a : b;
}

/** What the browser knows about the hub's answer and the hub's clock. */
export interface Freshness {
  /** Browser time (ms) when the node list on screen was fetched. */
  fetchedAt?: number;
  /** Hub clock minus browser clock (ms), from the response Date header; undefined if unknown. */
  hubOffsetMs?: number;
}

/** "now" on the hub's clock when the offset is known, else the browser's (display only). */
export function hubNow(now: number, f: Freshness): number {
  return now + (f.hubOffsetMs ?? 0);
}

/**
 * The status we show. The gateway decides freshness on its own clock (§3), and
 * `last_seen` is stamped by that clock, so it is never compared with the
 * browser's clock directly (a skewed browser would mark healthy nodes stale).
 * The gateway's answer can only get worse, by:
 * - the time since it was fetched (browser clock at both ends, so skew-free),
 *   for a tab left open or a failed poll;
 * - `last_seen` aged against hub time, when the hub clock offset is known.
 * A value is never shown as live just because the last response said so.
 */
export function effectiveStatus(server: NodeStatus, lastSeen: string, now: number, f: Freshness = {}): NodeStatus {
  if (Number.isNaN(Date.parse(lastSeen))) return 'offline';
  let status = server;
  if (f.fetchedAt !== undefined) status = worse(status, fromAge(Math.max(0, (now - f.fetchedAt) / 1000)));
  if (f.hubOffsetMs !== undefined) status = worse(status, fromAge(secondsSince(lastSeen, hubNow(now, f)) ?? Infinity));
  return status;
}

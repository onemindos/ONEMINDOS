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

/**
 * The status we show. The gateway decides freshness, but its answer itself ages
 * in the browser (a tab left open, a failed poll). So we take the WORSE of the
 * gateway's status and what last_seen says right now. A value is never shown
 * as live just because the last response said so.
 */
export function effectiveStatus(server: NodeStatus, lastSeen: string, now: number): NodeStatus {
  const age = secondsSince(lastSeen, now);
  let local: NodeStatus = 'offline';
  if (age !== null) local = age >= OFFLINE_AFTER_S ? 'offline' : age >= STALE_AFTER_S ? 'stale' : 'online';
  return RANK[local] > RANK[server] ? local : server;
}

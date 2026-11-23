// SPDX-License-Identifier: Apache-2.0
// Home health card helpers: one row per `GET /v1/status` source, the live indicator and the Open address.
// Pure functions so the rules (unknown is never ok, age shown, Open only with an address) are tested directly.
import type { CatalogApp, HealthState, SourceStatus, StatusView } from '../api/types';
import type { StreamState } from './events';
import { formatAgo, secondsSince } from './time';

export type HealthSource = 'alerts' | 'approvals' | 'apps' | 'storage' | 'backups' | 'updates' | 'mesh';

export type HealthTarget = { tab: 'Approvals' | 'Apps' } | { screen: 'Inbox' | 'Nodes' | 'Backups' | 'OsUpdates' };

export const HEALTH_ROWS: ReadonlyArray<{ source: HealthSource; label: string; to: HealthTarget }> = [
  { source: 'alerts', label: 'Alerts', to: { screen: 'Inbox' } },
  { source: 'approvals', label: 'Approvals', to: { tab: 'Approvals' } },
  { source: 'apps', label: 'Apps', to: { tab: 'Apps' } },
  { source: 'storage', label: 'Storage', to: { screen: 'Nodes' } },
  { source: 'backups', label: 'Backups', to: { screen: 'Backups' } },
  { source: 'updates', label: 'Updates', to: { screen: 'OsUpdates' } },
  { source: 'mesh', label: 'Mesh', to: { screen: 'Nodes' } },
];

const KNOWN: ReadonlySet<string> = new Set(['ok', 'attention', 'critical', 'unknown']);

/** Anything the phone does not recognise is shown as unknown, never as ok. */
export function healthState(s: string | undefined): HealthState {
  return s !== undefined && KNOWN.has(s) ? (s as HealthState) : 'unknown';
}

export const HEALTH_WORD: Record<HealthState, string> = { ok: 'OK', attention: 'Needs attention', critical: 'Critical', unknown: 'Unknown' };
export const HEALTH_TONE: Record<HealthState, 'ok' | 'warn' | 'bad' | 'neutral'> = { ok: 'ok', attention: 'warn', critical: 'bad', unknown: 'neutral' };

export interface HealthRowView {
  source: HealthSource;
  label: string;
  state: HealthState;
  summary: string;
  /** "12s ago", or "unknown" when the hub gave no read time. */
  age: string;
  to: HealthTarget;
}

/** Age is measured on the hub clock: `now` is phone time, `hubOffsetMs` the hub minus phone difference. */
export function healthRows(status: StatusView, now: number, hubOffsetMs = 0): HealthRowView[] {
  return HEALTH_ROWS.map(({ source, label, to }) => {
    const src: SourceStatus | undefined = status[source];
    const state = healthState(src?.state);
    return {
      source,
      label,
      state,
      summary: src?.summary || (state === 'unknown' ? 'Could not be read' : ''),
      age: src?.observed_at ? formatAgo(secondsSince(src.observed_at, now + hubOffsetMs)) : 'unknown',
      to,
    };
  });
}

export type LiveIndicator = 'live' | 'reconnecting' | 'polling';

/** Event stream state to the three words the person sees. */
export function liveIndicator(s: StreamState | 'off'): LiveIndicator {
  if (s === 'open') return 'live';
  if (s === 'connecting' || s === 'retrying') return 'reconnecting';
  return 'polling';
}

export const LIVE_WORD: Record<LiveIndicator, string> = { live: 'Live', reconnecting: 'Reconnecting', polling: 'Polling' };

/**
 * Where an installed app answers: its `web_port` on the box host. Nothing for an app that is not installed,
 * has no port, or when the hub address is unknown (demo). The web address is opened in the system browser.
 */
export function appOpenUrl(app: Pick<CatalogApp, 'installed' | 'web_port'>, hubUrl: string | undefined): string | undefined {
  if (!app.installed || !app.web_port || !Number.isInteger(app.web_port) || app.web_port < 1 || app.web_port > 65535 || !hubUrl) return undefined;
  try {
    const u = new URL(hubUrl);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return undefined;
    return `${u.protocol}//${u.hostname.includes(':') ? `[${u.hostname.replace(/^\[|\]$/g, '')}]` : u.hostname}:${app.web_port}/`;
  } catch {
    return undefined;
  }
}

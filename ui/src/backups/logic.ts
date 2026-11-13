// SPDX-License-Identifier: Apache-2.0
// Rules of the Backups and Restore screens, kept apart from the components so they are tested
// without rendering. Every time comparison takes `now` (the hub's clock) from the caller.
import type { Tone } from '../tokens/tokens';
import { formatAgo, secondsSince } from '../lib/time';
import type { BackupBadge, BackupsStatus, BadgeState, Destination, RunState, Snapshot } from './types';

export const BADGE: Record<BadgeState, { tone: Tone; label: string }> = {
  verified: { tone: 'ok', label: 'Verified' },
  unverified: { tone: 'warn', label: 'Backed up, not verified' },
  stale: { tone: 'warn', label: 'Stale' },
  failing: { tone: 'bad', label: 'Failing' },
  none: { tone: 'neutral', label: 'No backup' },
};

/** Badge with its age: a badge always says how old it is (BACKUPS.md §8). */
export function badgeView(b: BackupBadge | undefined, now: number): { tone: Tone; label: string; detail?: string } {
  const base = BADGE[b?.state ?? 'none'] ?? BADGE.none;
  if (!b) return base;
  if (b.state === 'verified' && b.verified_at) return { ...base, detail: `restore tested ${formatAgo(secondsSince(b.verified_at, now))}` };
  if (b.last_success_at) return { ...base, detail: `backed up ${formatAgo(secondsSince(b.last_success_at, now))}` };
  return base;
}

export const HEALTH: Record<BackupsStatus['health'], { tone: Tone; label: string }> = {
  ok: { tone: 'ok', label: 'Protected' },
  stale: { tone: 'warn', label: 'Behind' },
  failing: { tone: 'bad', label: 'Needs attention' },
  not_configured: { tone: 'neutral', label: 'Not set up' },
};

export const RUN: Record<RunState, { tone: Tone; label: string }> = {
  running: { tone: 'info', label: 'Running' },
  succeeded: { tone: 'ok', label: 'Done' },
  partial: { tone: 'warn', label: 'Partly done' },
  failed: { tone: 'bad', label: 'Failed' },
  refused: { tone: 'bad', label: 'Refused' },
};

export const REASON: Record<string, string> = {
  scheduled: 'Hourly',
  manual: 'Backup now',
  'pre-update': 'Before an update',
  'pre-restore': 'Before a restore (undo point)',
  'pre-delete': 'Before deleting data',
};

export const KIND_LABEL: Record<Destination['kind'], string> = {
  usb: 'USB disk',
  box: 'Another OneMind box',
  rest: 'restic REST server',
  s3: 'S3-compatible bucket',
};

/** One line saying where a destination is, without any secret. */
export function destinationWhere(d: Destination): string {
  const c = d.config;
  if (d.kind === 'usb') return `disk ${String(c.usb_uuid ?? '?')}`;
  if (d.kind === 's3') return [c.endpoint, c.bucket, c.prefix].filter(Boolean).join(' / ');
  return String(c.url ?? '');
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '–';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i += 1;
  }
  return `${i === 0 ? v : v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

/** "app:notes" -> "notes"; system units get words. */
export function unitLabel(unit: string): string {
  if (unit.startsWith('app:')) return unit.slice(4);
  if (unit === 'system') return 'OneMind settings and records';
  if (unit === 'k3s') return 'Kubernetes state';
  if (unit.startsWith('node:')) return `Machine ${unit.slice(5)}`;
  return unit;
}

/** Snapshots of one app (or all), newest first, grouped by UTC day. */
export function snapshotsByDay(snaps: Snapshot[], appId?: string): { day: string; items: Snapshot[] }[] {
  const out = new Map<string, Snapshot[]>();
  [...snaps]
    .filter((s) => !appId || s.app_id === appId)
    .sort((a, b) => Date.parse(b.taken_at) - Date.parse(a.taken_at))
    .forEach((s) => {
      const day = s.taken_at.slice(0, 10);
      out.set(day, [...(out.get(day) ?? []), s]);
    });
  return [...out].map(([day, items]) => ({ day, items }));
}

/** Breadcrumbs inside a snapshot: the volume root first, then each folder below it. */
export function breadcrumbs(path: string, roots: string[]): { label: string; path: string }[] {
  const root = roots.find((r) => path === r || path.startsWith(`${r}/`));
  if (!root) return [{ label: '/', path: '/' }];
  const rootLabel = volumeLabel(root);
  const rest = path.slice(root.length).split('/').filter(Boolean);
  const crumbs = [{ label: rootLabel, path: root }];
  let p = root;
  for (const part of rest) {
    p = `${p}/${part}`;
    crumbs.push({ label: part, path: p });
  }
  return crumbs;
}

/** A local-path folder <pv>_<namespace>_<claim> reads as "data (volume)". */
export function volumeLabel(path: string): string {
  const base = path.split('/').filter(Boolean).pop() ?? path;
  const m = /^pvc-[^_]+_([^_]+)_(.+)$/.exec(base);
  if (!m) return base;
  if (m[1] === 'onemind-db') return 'database dump';
  return `${m[2]} (volume)`;
}

/** The two groups to type back are filled and four letters each. */
export function typeBackReady(positions: number[], answers: Record<string, string>): boolean {
  return positions.length > 0 && positions.every((p) => /^[A-Z2-7]{4}$/.test((answers[String(p)] ?? '').trim().toUpperCase()));
}

export function normaliseAnswers(answers: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(answers).map(([k, v]) => [k, v.trim().toUpperCase()]));
}

export function kitFileName(boxName: string, issuedAt: string): string {
  const safe = boxName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'onemind';
  return `${safe}-emergency-kit-${issuedAt.slice(0, 10)}.txt`;
}

/** A whole-app restore needs the app's id typed: it stops the app and replaces its data. */
export function restoreConfirmed(scope: { app_id: string; path?: string }, typed: string): boolean {
  return scope.path !== undefined || typed.trim() === scope.app_id;
}

/** The request the Restore dialog sends, and the same call for the CLI-minded. */
export function restoreRequest(snapshotId: string, scope: { app_id: string; path?: string }, reason?: string) {
  const body = { snapshot_id: snapshotId, scope, ...(reason ? { reason } : {}) };
  return {
    method: 'POST' as const,
    path: '/v1/restores',
    body,
    curl: `curl -X POST "$HUB/v1/restores" -H "Authorization: Bearer $TOKEN" -d '${JSON.stringify(body)}'`,
  };
}

/** Whether the hub may still claim to be protected: stale data is never shown as live. */
export function overviewNotice(s: BackupsStatus): { tone: Tone; text: string } | null {
  if (s.agent === 'unreachable') return { tone: 'bad', text: 'The backup agent on the hub is not answering. Backups are not running.' };
  if (s.destinations.length === 0) return { tone: 'info', text: 'Add a backup destination to switch backups on.' };
  if (s.kit.state !== 'confirmed') return { tone: 'warn', text: 'Save your emergency kit. Without it, a lost box means lost backups.' };
  if (s.copies < 2) return { tone: 'info', text: 'One copy only. A second destination in another place protects against fire and theft.' };
  return null;
}

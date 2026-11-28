// SPDX-License-Identifier: Apache-2.0
// Atlas Files (prototype 07): how many copies of a file exist, read from GET /v1/backups/status
// (destinations, which one is primary, whether the Files built-in's folders are carried) and
// GET /v1/backups/runs (each run's destination, its `system` unit state and the built-ins export hook).
// Both schemas are unconstrained, so every field is checked here and nothing is invented.
//
// The rule, in plain words (gate decision on #1350, option b): a file is on the box (one copy). It is
// also on the PRIMARY destination when a run to the primary, whose `system` unit succeeded and whose
// built-ins export hook succeeded (that is what carries Files), started after the file last changed.
// That makes two copies. Other destinations get a run once a day (internal/backup/schedule.go) and the
// status does not say per destination whether that run worked, so they are named, never counted.
// A destination with no such run yet (just added) is never counted. Folders get no count: a folder's
// own time says nothing about the files inside it.

/** The built-ins export the gateway writes before a `system` snapshot (core backups/units.py EXPORT_FILE). */
export const EXPORT_FILE = 'builtin-units.tar';

export interface BackupDestination { id: string; label: string; kind: string; primary: boolean }
export interface BackupState {
  primary: BackupDestination | undefined;
  others: BackupDestination[];
  /** Start of the newest run to the primary that carried Files, or null. */
  lastPrimaryCopyAt: string | null;
  nextRunAt: string | null;
}

export type Copies =
  | { kind: 'copied'; count: 2; at: string; primary: string }
  | { kind: 'waiting'; next: string | null }
  | { kind: 'none' }
  | { kind: 'folder' };

const iso = (v: unknown): string | null => (typeof v === 'string' && v && !Number.isNaN(Date.parse(v)) ? v : null);
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const arr = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.map(rec) : []);

/** A run that put Files on its destination: the `system` unit succeeded and the built-ins export before it did too. */
export function carriedFiles(run: Record<string, unknown>): boolean {
  return arr(run.units).some((u) => u.unit === 'system' && u.state === 'succeeded')
    && arr(run.hooks).some((h) => h.unit === 'builtins' && h.command === EXPORT_FILE && h.ok === true);
}

export function toBackupState(rawStatus: unknown, rawRuns: unknown): BackupState {
  if (!rawStatus || typeof rawStatus !== 'object' || Array.isArray(rawStatus)) throw new Error('The hub returned an invalid backup status.');
  if (!Array.isArray(rawRuns)) throw new Error('The hub returned an invalid list of backup runs.');
  const s = rawStatus as Record<string, unknown>;
  const dests = arr(s.destinations).filter((d) => typeof d.id === 'string').map((d) => ({
    id: d.id as string,
    label: typeof d.label === 'string' && d.label ? d.label : typeof d.kind === 'string' ? d.kind : 'Destination',
    kind: typeof d.kind === 'string' ? d.kind : 'unknown',
    primary: d.primary === true,
  }));
  const primary = dests.find((d) => d.primary);
  // The Files folders must be set up to travel with the system unit; otherwise no run carries them.
  const files = arr(s.builtin_units).find((u) => u.unit === 'builtin:files');
  const foldersCarried = !!files && arr(files.dirs).every((d) => d.configured !== true || d.carried === true);
  let last: number | null = null;
  if (primary && foldersCarried) {
    for (const r of rawRuns.map(rec)) {
      const at = iso(r.started_at);
      if (r.destination_id === primary.id && at && carriedFiles(r) && (last === null || Date.parse(at) > last)) last = Date.parse(at);
    }
  }
  return { primary, others: dests.filter((d) => d !== primary), lastPrimaryCopyAt: last === null ? null : new Date(last).toISOString(), nextRunAt: iso(s.next_run_at) };
}

export function copiesOf(entry: { type: string; mtime: string }, s: BackupState | undefined): Copies | undefined {
  if (!s) return undefined;
  if (entry.type === 'dir') return { kind: 'folder' };
  if (!s.primary) return { kind: 'none' };
  const changed = Date.parse(entry.mtime);
  if (s.lastPrimaryCopyAt && !Number.isNaN(changed) && changed < Date.parse(s.lastPrimaryCopyAt))
    return { kind: 'copied', count: 2, at: s.lastPrimaryCopyAt, primary: s.primary.label };
  return { kind: 'waiting', next: s.nextRunAt };
}

/** "02:10" in the viewer's clock, or the date when it is not today. */
export function clock(isoTime: string, now = Date.now()): string {
  const d = new Date(isoTime);
  const sameDay = d.toDateString() === new Date(now).toDateString();
  const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  return sameDay ? hm : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${hm}`;
}

export function copiesLabel(c: Copies, now = Date.now()): string {
  switch (c.kind) {
    case 'copied': return `${c.count} copies`;
    case 'waiting': return c.next ? `1 copy · next ${clock(c.next, now)}` : '1 copy · waiting';
    case 'none': return '1 copy · no backup';
    case 'folder': return '';
  }
}

/** The footer line: how many files are on the box and the primary, and how many wait. */
export function copiesSummary(entries: Array<{ type: string; mtime: string }>, s: BackupState | undefined): { copied: number; waiting: number; next: string | null } | undefined {
  if (!s) return undefined;
  let copied = 0, waiting = 0;
  for (const e of entries) {
    const c = copiesOf(e, s);
    if (c?.kind === 'copied') copied++;
    else if (c?.kind === 'waiting' || c?.kind === 'none') waiting++;
  }
  return { copied, waiting, next: s.nextRunAt };
}

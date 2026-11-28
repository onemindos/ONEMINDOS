// SPDX-License-Identifier: Apache-2.0
// Atlas Files (prototype 07): how many copies of a file exist, read from GET /v1/backups/status.
// The status schema is unconstrained, so every field is checked here and nothing is invented.
//
// The rule, in plain words: a file is on the box (one copy). It is also in every backup destination
// when the Files built-in is carried by the last successful snapshot (`builtin_units[builtin:files]
// .in_snapshot`, set by the gateway only after the agent reports it), backups are healthy, and the file
// last changed before that snapshot. Otherwise it waits for the next run. Folders get no count: a
// folder's own time says nothing about the files inside it.

export interface BackupDestination { id: string; label: string; kind: string }
export interface BackupState {
  health: string;
  /** Number of backup destinations (the gateway's `copies`). */
  destinations: BackupDestination[];
  /** When the snapshot that carries the Files built-in last succeeded (the system unit), or null. */
  lastCopyAt: string | null;
  nextRunAt: string | null;
  /** The Files built-in is in the last successful snapshot. */
  filesCarried: boolean;
}

export type Copies =
  | { kind: 'copied'; count: number; at: string }
  | { kind: 'waiting'; next: string | null }
  | { kind: 'none' }
  | { kind: 'folder' };

const iso = (v: unknown): string | null => (typeof v === 'string' && v && !Number.isNaN(Date.parse(v)) ? v : null);
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

export function toBackupState(raw: unknown): BackupState {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('The hub returned an invalid backup status.');
  const s = raw as Record<string, unknown>;
  const destinations = (Array.isArray(s.destinations) ? s.destinations : []).map(rec).filter((d) => typeof d.id === 'string').map((d) => ({
    id: d.id as string,
    label: typeof d.label === 'string' && d.label ? d.label : typeof d.kind === 'string' ? d.kind : 'Destination',
    kind: typeof d.kind === 'string' ? d.kind : 'unknown',
  }));
  const units = Array.isArray(s.builtin_units) ? s.builtin_units.map(rec) : [];
  const files = units.find((u) => u.unit === 'builtin:files');
  const system = rec(rec(s.badges).system);
  return {
    health: typeof s.health === 'string' ? s.health : 'unknown',
    destinations,
    lastCopyAt: iso(system.last_success_at) ?? null,
    nextRunAt: iso(s.next_run_at),
    filesCarried: files?.in_snapshot === true,
  };
}

export function copiesOf(entry: { type: string; mtime: string }, s: BackupState | undefined): Copies | undefined {
  if (!s) return undefined;
  if (entry.type === 'dir') return { kind: 'folder' };
  if (s.destinations.length === 0) return { kind: 'none' };
  const changed = Date.parse(entry.mtime);
  if (s.health === 'ok' && s.filesCarried && s.lastCopyAt && !Number.isNaN(changed) && changed <= Date.parse(s.lastCopyAt))
    return { kind: 'copied', count: 1 + s.destinations.length, at: s.lastCopyAt };
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

/** The footer line: how many files have every copy and how many wait. */
export function copiesSummary(entries: Array<{ type: string; mtime: string }>, s: BackupState | undefined): { copied: number; count: number; waiting: number; next: string | null } | undefined {
  if (!s) return undefined;
  let copied = 0, waiting = 0;
  for (const e of entries) {
    const c = copiesOf(e, s);
    if (c?.kind === 'copied') copied++;
    else if (c?.kind === 'waiting' || c?.kind === 'none') waiting++;
  }
  return { copied, count: 1 + s.destinations.length, waiting, next: s.nextRunAt };
}

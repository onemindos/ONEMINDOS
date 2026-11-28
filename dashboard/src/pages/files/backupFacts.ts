// SPDX-License-Identifier: Apache-2.0
// Atlas Files (prototype 07): facts about backup RUNS for the sidebar and footer, read from
// GET /v1/backups/status (destinations, which is primary, the system badge, whether the Files folders
// travel with the system unit) and GET /v1/backups/runs (destination, `system` unit state, built-ins
// export hook). Both schemas are unconstrained, so every field is checked and nothing is invented.
//
// No per-file copy count (review on #1350): a file's mtime can be backdated (Samba, rsync, cp -p, a
// snapshot restore), and the repo rejects mtime for this (core/onemind_core/filesig.py). The count
// returns once /v1/files/list carries ctime, compared with the run start. Until then the page only says
// when the last run to the primary that carried Files started, which is a fact about the run.

/** The built-ins export the gateway writes before a `system` snapshot (core backups/units.py EXPORT_FILE). */
export const EXPORT_FILE = 'builtin-units.tar';

export interface BackupDestination { id: string; label: string; kind: string; primary: boolean }
export interface BackupState {
  primary: BackupDestination | undefined;
  others: BackupDestination[];
  /** Start of the newest run to the primary that carried Files, or null. */
  lastPrimaryCopyAt: string | null;
  nextRunAt: string | null;
  /** badges.system.state is failing: say backups need attention, not a time. */
  failing: boolean;
}

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
  return { primary, others: dests.filter((d) => d !== primary), lastPrimaryCopyAt: last === null ? null : new Date(last).toISOString(), nextRunAt: iso(s.next_run_at), failing: rec(rec(s.badges).system).state === 'failing' };
}

/** "02:10" in the viewer's clock, or the date when it is not today. */
export function clock(isoTime: string, now = Date.now()): string {
  const d = new Date(isoTime);
  const sameDay = d.toDateString() === new Date(now).toDateString();
  const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  return sameDay ? hm : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${hm}`;
}

// SPDX-License-Identifier: Apache-2.0
// Quick settings (#841): turns each gateway answer into one read-only tile. Nothing is invented: a
// route that fails, a field that is missing or a value the node could not measure reads "Unknown"
// and never a green state (PRINCIPLES P2).
export type TileTone = 'ok' | 'warn' | 'bad' | 'unknown';
export interface TileValue {
  value: string;
  tone: TileTone;
}
export const UNKNOWN: TileValue = { value: 'Unknown', tone: 'unknown' };

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown) => (typeof v === 'string' && v ? v : null);

/** "1.5 TB", "320 GB": decimal units, as disks are sold. */
export function formatBytes(n: number): string {
  const units = ['B', 'kB', 'MB', 'GB', 'TB', 'PB'];
  let v = n;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i++;
  }
  return `${i === 0 || v >= 100 ? Math.round(v) : Math.round(v * 10) / 10} ${units[i]}`;
}

/** GET /v1/storage: the measured free bytes the filesystem reports after mirroring; null is Unknown. */
export function storageTile(raw: unknown): TileValue {
  if (!isRec(raw) || raw.enabled !== true || raw.available !== true) return UNKNOWN;
  const free = raw.available_bytes;
  if (typeof free !== 'number' || !Number.isFinite(free) || free < 0) return UNKNOWN;
  return { value: `${formatBytes(free)} free`, tone: 'ok' };
}

/** GET /v1/network: Unknown unless the host service answered; "Online" needs an interface that is up. */
export function networkTile(raw: unknown): TileValue {
  if (!isRec(raw) || raw.available !== true || !Array.isArray(raw.interfaces)) return UNKNOWN;
  const up = raw.interfaces.filter((i) => isRec(i) && i.state === 'up').length;
  return up > 0 ? { value: 'Connected', tone: 'ok' } : { value: 'No link', tone: 'bad' };
}

/** GET /v1/os/updates: how many nodes have an update on offer. */
export function updatesTile(raw: unknown): TileValue {
  if (!isRec(raw) || !Array.isArray(raw.nodes)) return UNKNOWN;
  const waiting = raw.nodes.filter((n) => isRec(n) && str(n.available_version)).length;
  return waiting === 0 ? { value: 'Up to date', tone: 'ok' } : { value: `${waiting} waiting`, tone: 'warn' };
}

/** GET /v1/backups/status: the last success, or why there is none. */
export function backupTile(raw: unknown, now: number): TileValue {
  if (!isRec(raw) || typeof raw.health !== 'string') return UNKNOWN;
  if (raw.health === 'failing') return { value: 'Failing', tone: 'bad' };
  const last = str(raw.last_success_at);
  if (raw.health === 'not_configured' || !last) return { value: 'Not set up', tone: 'warn' };
  const days = Math.floor((now - Date.parse(last)) / 86_400_000);
  if (!Number.isFinite(days)) return UNKNOWN;
  return { value: days <= 0 ? 'Today' : days === 1 ? 'Yesterday' : `${days} days ago`, tone: days > 7 ? 'warn' : 'ok' };
}

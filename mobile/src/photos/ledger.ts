// SPDX-License-Identifier: Apache-2.0
// The phone's record of what it has sent: one entry per library item, the open upload address
// for an unfinished item, and the last run. It holds no photo bytes and no token. The box's
// receipts stay the truth (a lost ledger only costs a re-check, never a duplicate upload).
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils.js';
import type { Coverage } from './protocol';
import type { AlbumSelection } from './media';

export type ItemState = 'pending' | 'done' | 'failed';

export interface LedgerItem {
  /** 64-hex key sent to the box; derived from this install's id and the platform id, so it reveals neither. */
  key: string;
  fileName: string;
  modifiedAt: number;
  inSelection: boolean;
  size?: number;
  hash?: string;
  state: ItemState;
  /** True when the box already had the bytes and nothing was uploaded. */
  deduped?: boolean;
  upload?: { url: string };
  error?: string;
  attempts?: number;
  doneAt?: number;
}

export type RunOutcome = 'completed' | 'stopped' | 'blocked' | 'error';

export interface RunRecord {
  trigger: 'foreground' | 'background' | 'manual';
  startedAt: number;
  endedAt: number;
  outcome: RunOutcome;
  /** Machine reason, e.g. needs_wifi, connection_lost; mapped to words in status.ts. */
  reason?: string;
  message?: string;
  uploaded: number;
  deduped: number;
  bytes: number;
}

export interface Ledger {
  version: 1;
  clientId: string;
  sourceId?: string;
  items: Record<string, LedgerItem>;
  scan?: { at: number; total: number };
  lastRun?: RunRecord;
  /** Phone time when every selected item was last confirmed on the box. */
  lastComplete?: number;
  coverage?: Coverage & { fetchedAt: number };
}

export interface BackupSettings {
  enabled: boolean;
  wifiOnly: boolean;
  chargingOnly: boolean;
  albums: AlbumSelection;
}

export const DEFAULT_SETTINGS: BackupSettings = { enabled: false, wifiOnly: true, chargingOnly: false, albums: 'all' };

export function parseSettings(raw: string | null): BackupSettings {
  if (!raw) return { ...DEFAULT_SETTINGS };
  try {
    const v = JSON.parse(raw) as Partial<BackupSettings>;
    return {
      enabled: v.enabled === true,
      wifiOnly: v.wifiOnly !== false,
      chargingOnly: v.chargingOnly === true,
      albums: Array.isArray(v.albums) && v.albums.every((x) => typeof x === 'string') ? v.albums : 'all',
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function newLedger(clientId: string): Ledger {
  return { version: 1, clientId, items: {} };
}

export function parseLedger(raw: string | null): Ledger | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Ledger;
    if (v.version !== 1 || typeof v.clientId !== 'string' || typeof v.items !== 'object' || v.items === null) return null;
    return v;
  } catch {
    return null;
  }
}

export function clientKey(clientId: string, assetId: string): string {
  return bytesToHex(sha256(utf8ToBytes(`onemind-photos-key/v1\n${clientId}\n${assetId}`)));
}

/** Where settings and the ledger live. The app uses files in its sandbox; tests use memory. */
export interface BackupStore {
  loadLedger(): Promise<Ledger | null>;
  saveLedger(l: Ledger): Promise<void>;
  loadSettings(): Promise<BackupSettings>;
  saveSettings(s: BackupSettings): Promise<void>;
}

export class MemoryStore implements BackupStore {
  ledger: string | null = null;
  settings: string | null = null;
  saves = 0;
  async loadLedger() {
    return parseLedger(this.ledger);
  }
  async saveLedger(l: Ledger) {
    this.saves++;
    this.ledger = JSON.stringify(l);
  }
  async loadSettings() {
    return parseSettings(this.settings);
  }
  async saveSettings(s: BackupSettings) {
    this.settings = JSON.stringify(s);
  }
}

export interface Counts {
  total: number;
  done: number;
  waiting: number;
  failed: number;
}

export function counts(l: Ledger | null | undefined): Counts {
  const c: Counts = { total: 0, done: 0, waiting: 0, failed: 0 };
  for (const it of Object.values(l?.items ?? {})) {
    if (!it.inSelection) continue;
    c.total++;
    if (it.state === 'done') c.done++;
    else if (it.state === 'failed') c.failed++;
    else c.waiting++;
  }
  return c;
}

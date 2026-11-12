// SPDX-License-Identifier: Apache-2.0
// One backup run: check the rules, scan the selected albums, hash what is new, ask the box which
// items it already has (dedupe by hash), and upload the rest in resumable chunks. Each run does
// as much as its time allows and stops cleanly; the next run continues from the box's offset.
// The same function runs in the foreground and from the OS background task.
import { ApiError } from '../api/types';
import { uuidv4 } from '../lib/uuid';
import { clientKey, newLedger, type BackupSettings, type BackupStore, type Ledger, type LedgerItem, type RunRecord } from './ledger';
import type { MediaAsset, MediaSource } from './media';
import { MAX_CHECK, type Platform, type PhotosApi } from './protocol';

export type NetworkKind = 'wifi' | 'cellular' | 'other' | 'none';
export type PowerKind = 'charging' | 'battery' | 'unknown';

export interface Conditions {
  network: NetworkKind;
  power: PowerKind;
}

export type BlockReason = 'disabled' | 'no_permission' | 'offline' | 'needs_wifi' | 'needs_charging';

export function blockReason(s: BackupSettings, c: Conditions): BlockReason | undefined {
  if (!s.enabled) return 'disabled';
  if (c.network === 'none') return 'offline';
  if (s.wifiOnly && c.network !== 'wifi') return 'needs_wifi';
  if (s.chargingOnly && c.power !== 'charging') return 'needs_charging';
  return undefined;
}

export interface Progress {
  phase: 'scanning' | 'hashing' | 'checking' | 'uploading';
  /** Items confirmed on the box, of `total` selected. */
  done: number;
  total: number;
  current?: { fileName: string; sent: number; size: number };
  bytesThisRun: number;
}

export interface RunDeps {
  api: PhotosApi;
  media: MediaSource;
  store: BackupStore;
  settings: BackupSettings;
  conditions: () => Promise<Conditions>;
  platform: Platform;
  deviceName: string;
  trigger: RunRecord['trigger'];
  now?: () => number;
  /** Phone time (ms) after which no new chunk starts. */
  deadline?: number;
  signal?: { aborted: boolean };
  chunkSize?: number;
  onProgress?: (p: Progress) => void;
  /** Ledger writes are throttled to this interval while uploading (ms). */
  saveEveryMs?: number;
}

export const DEFAULT_CHUNK = 4 * 1024 * 1024;
const MAX_ATTEMPTS = 3;

class Stop extends Error {
  constructor(
    readonly outcome: RunRecord['outcome'],
    readonly reason: string,
    message?: string,
  ) {
    super(message ?? reason);
  }
}

let running: Promise<RunRecord> | undefined;

/** Only one run at a time per app process (foreground and background share the ledger). */
export function runBackup(d: RunDeps): Promise<RunRecord> {
  if (running) return running;
  running = runInner(d).finally(() => {
    running = undefined;
  });
  return running;
}

export function isRunning(): boolean {
  return running !== undefined;
}

async function runInner(d: RunDeps): Promise<RunRecord> {
  const now = d.now ?? Date.now;
  const chunk = d.chunkSize ?? DEFAULT_CHUNK;
  const L: Ledger = (await d.store.loadLedger()) ?? newLedger(uuidv4());
  const rec: RunRecord = { trigger: d.trigger, startedAt: now(), endedAt: now(), outcome: 'completed', uploaded: 0, deduped: 0, bytes: 0 };
  let lastSave = 0;
  const save = async (force = false) => {
    if (!force && now() - lastSave < (d.saveEveryMs ?? 2000)) return;
    lastSave = now();
    await d.store.saveLedger(L);
  };
  const doneCount = () => Object.values(L.items).filter((i) => i.inSelection && i.state === 'done').length;
  let total = 0;
  const progress = (phase: Progress['phase'], current?: Progress['current']) =>
    d.onProgress?.({ phase, done: doneCount(), total, current, bytesThisRun: rec.bytes });

  const checkpoint = async () => {
    if (d.signal?.aborted) throw new Stop('stopped', 'cancelled');
    if (d.deadline !== undefined && now() >= d.deadline) throw new Stop('stopped', 'time_up');
    const b = blockReason(d.settings, await d.conditions());
    if (b) throw new Stop('blocked', b);
  };

  try {
    await checkpoint();
    const perm = await d.media.permission(false);
    if (perm !== 'granted' && perm !== 'limited') throw new Stop('blocked', 'no_permission');

    if (!L.sourceId) {
      const src = await d.api.registerSource({ client_id: L.clientId, name: d.deviceName, platform: d.platform });
      L.sourceId = src.id;
      await save(true);
    }
    const sourceId = L.sourceId;

    // 1. Scan: reconcile the ledger with the selected albums.
    progress('scanning');
    const assets = await d.media.list(d.settings.albums);
    const byId = new Map<string, MediaAsset>();
    for (const a of assets) byId.set(a.id, a);
    for (const [id, it] of Object.entries(L.items)) if (!byId.has(id)) it.inSelection = false;
    for (const a of assets) {
      const it = L.items[a.id];
      if (!it || it.modifiedAt !== a.modifiedAt)
        L.items[a.id] = { key: clientKey(L.clientId, a.id), fileName: a.fileName, modifiedAt: a.modifiedAt, inSelection: true, state: 'pending' };
      else {
        it.inSelection = true;
        if (it.state === 'failed' && (it.attempts ?? 0) < MAX_ATTEMPTS) it.state = 'pending';
      }
    }
    total = assets.length;
    L.scan = { at: now(), total };
    await save(true);

    const todo = assets.filter((a) => L.items[a.id]!.state === 'pending');

    // 2. Hash and check in batches; anything the box already has is done without an upload.
    const need: MediaAsset[] = [];
    for (let i = 0; i < todo.length; i += MAX_CHECK) {
      const batch = todo.slice(i, i + MAX_CHECK);
      for (const a of batch) {
        await checkpoint();
        const it = L.items[a.id]!;
        if (!it.hash || it.size === undefined) {
          progress('hashing', { fileName: a.fileName, sent: 0, size: 0 });
          try {
            it.size = await d.media.size(a);
            it.hash = await d.media.hash(a);
          } catch (e) {
            fail(it, e);
          }
          if (it.size === 0) fail(it, new Error('The file is empty'));
        }
      }
      const ask = batch.map((a) => L.items[a.id]!).filter((it) => it.state === 'pending' && it.hash && it.size);
      if (ask.length) {
        progress('checking');
        const answers = await d.api.check(sourceId, ask.map((it) => ({ client_key: it.key, size: it.size!, hash: it.hash! })));
        const have = new Set(answers.filter((x) => x.status === 'have').map((x) => x.client_key));
        for (const a of batch) {
          const it = L.items[a.id]!;
          if (it.state !== 'pending') continue;
          if (have.has(it.key)) markDone(it, true);
          else need.push(a);
        }
      }
      await save(true);
    }

    // 3. Upload what the box needs, one item at a time, in chunks.
    const sentThisRun = new Set<string>();
    for (const a of need) {
      await checkpoint();
      const it = L.items[a.id]!;
      if (it.state !== 'pending') continue;
      if (sentThisRun.has(it.hash!)) {
        // A duplicate of something uploaded moments ago: the box records it without bytes.
        const [ans] = await d.api.check(sourceId, [{ client_key: it.key, size: it.size!, hash: it.hash! }]);
        if (ans?.status === 'have') {
          markDone(it, true);
          await save(true);
          continue;
        }
      }
      try {
        await uploadOne(a, it);
        sentThisRun.add(it.hash!);
      } catch (e) {
        if (e instanceof Stop) throw e;
        if (e instanceof ApiError && (e.code === 'network' || e.code === 'unauthenticated' || e.status >= 500))
          throw new Stop('stopped', e.code === 'unauthenticated' ? 'unauthenticated' : 'connection_lost', e.message);
        fail(it, e);
        it.upload = undefined;
      }
      await save(true);
    }

    const c = Object.values(L.items).filter((i) => i.inSelection);
    if (c.every((i) => i.state === 'done')) L.lastComplete = now();
  } catch (e) {
    if (e instanceof Stop) {
      rec.outcome = e.outcome;
      rec.reason = e.reason;
      rec.message = e.message;
    } else {
      rec.outcome = 'error';
      if (e instanceof ApiError) {
        rec.reason = e.code === 'network' ? 'connection_lost' : e.code;
        rec.message = e.message;
      } else {
        rec.reason = 'unexpected';
        rec.message = e instanceof Error ? e.message : String(e);
      }
    }
  }
  // Coverage is worth asking for after any run that reached the box, not only a complete one.
  if (rec.outcome !== 'error' && rec.reason !== 'connection_lost' && rec.reason !== 'unauthenticated' && rec.reason !== 'offline') await refreshCoverage();
  rec.endedAt = now();
  L.lastRun = rec;
  await d.store.saveLedger(L);
  return rec;

  function markDone(it: LedgerItem, deduped: boolean) {
    it.state = 'done';
    it.deduped = deduped;
    it.doneAt = now();
    it.upload = undefined;
    it.error = undefined;
    if (deduped) rec.deduped++;
    else rec.uploaded++;
  }

  function fail(it: LedgerItem, e: unknown) {
    it.state = 'failed';
    it.attempts = (it.attempts ?? 0) + 1;
    it.error = e instanceof Error ? e.message : String(e);
  }

  async function refreshCoverage() {
    if (!L.sourceId) return;
    try {
      L.coverage = { ...(await d.api.coverage(L.sourceId)), fetchedAt: now() };
    } catch {
      /* keep the old figures; status.ts shows their age */
    }
  }

  async function uploadOne(a: MediaAsset, it: LedgerItem) {
    const size = it.size!;
    let offset = 0;
    if (it.upload) {
      try {
        const st = await d.api.uploadOffset(it.upload.url);
        offset = st.offset;
      } catch (e) {
        if (e instanceof ApiError && e.code === 'not_found') it.upload = undefined;
        else throw e;
      }
    }
    if (!it.upload) {
      const url = await d.api.createUpload({ sourceId: L.sourceId!, clientKey: it.key, hash: it.hash!, size, fileName: a.fileName, createdAt: a.createdAt });
      it.upload = { url };
      offset = 0;
      await save(true);
    }
    let conflicts = 0;
    for (;;) {
      progress('uploading', { fileName: a.fileName, sent: offset, size });
      if (offset > 0 || conflicts > 0) await checkpoint();
      const len = Math.min(chunk, size - offset);
      const bytes = await d.media.read(a, offset, len);
      if (bytes.length !== len) throw new Error('The file changed while it was being read');
      const last = offset + len >= size;
      let r: Awaited<ReturnType<PhotosApi['appendChunk']>>;
      try {
        r = await d.api.appendChunk(it.upload.url, offset, bytes, last);
      } catch (e) {
        if (e instanceof ApiError && e.code === 'conflict' && conflicts < 3) {
          // Offset disagreement (e.g. a chunk that half-arrived before a drop): ask the box.
          conflicts++;
          const st = await d.api.uploadOffset(it.upload.url).catch(() => undefined);
          if (st && !st.complete) {
            offset = st.offset;
            continue;
          }
        }
        throw e;
      }
      rec.bytes += r.offset - offset;
      offset = r.offset;
      if (r.receipt) {
        if (r.receipt.hash !== it.hash) throw new Error('The box stored different bytes than the phone sent');
        markDone(it, r.receipt.deduped);
        progress('uploading', { fileName: a.fileName, sent: size, size });
        return;
      }
      await save();
    }
  }
}

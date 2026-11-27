// SPDX-License-Identifier: Apache-2.0
// The OneMind Sync client loop (docs/design/SYNC.md §7): edits go to the local cache and the outbox at
// once, so the app works offline; sync() sends the outbox, then reads the feed from the saved cursor.
import type { SyncStorage } from './storage.ts';
import type { Base, CachedItem, ItemView, OutboxEntry, Transport } from './types.ts';

export const PUSH_MAX = 100;
export const PAGE = 200;

/** An HTTP answer from the box. 4xx other than 408 and 429 will not get better by trying again. */
export class SyncHttpError extends Error {
  readonly status: number;
  readonly reason: string | null;
  constructor(status: number, reason: string | null, message: string) {
    super(message);
    this.status = status;
    this.reason = reason;
  }
}
export const retryable = (e: unknown) =>
  !(e instanceof SyncHttpError) || e.status >= 500 || e.status === 408 || e.status === 429;

export interface SyncOptions<R> {
  app: string;
  storage: SyncStorage;
  transport: Transport<R>;
  now?: () => number;
  newKey?: () => string;
  sleep?: (ms: number) => Promise<void>;
  backoff?: { baseMs: number; maxMs: number; attempts: number };
}

export interface SyncReport { pushed: number; conflicts: number; pulled: number; attempts: number }

const resolved = (b: Base): b is number | null => b === null || typeof b === 'number';

export class SyncClient<R> {
  private o: SyncOptions<R>;
  private now: () => number;
  constructor(o: SyncOptions<R>) { this.o = o; this.now = o.now ?? Date.now; }

  save(id: string, data: R) { return this.change(id, 'upsert', data); }
  remove(id: string) { return this.change(id, 'delete', null); }

  /** Record a change locally. The key is fixed now, so every later retry is the same operation. */
  private async change(id: string, op: 'upsert' | 'delete', data: R | null): Promise<void> {
    const { app, storage: s } = this.o;
    const item: CachedItem<R> = (await s.getItem<R>(app, id)) ?? { id, server: null, local: null };
    const box = await s.outbox<R>(app);
    const last = box.filter((e) => e.itemId === id).pop();
    if (last && !last.sent) {
      await s.putEntry<R>(app, { ...last, op, data }); // never left the device: fold the new edit in
    } else {
      const key = this.o.newKey ? this.o.newKey() : globalThis.crypto.randomUUID();
      const base: Base = last ? { after: last.key } : (item.server?.version ?? null);
      await s.putEntry<R>(app, { key, seq: (box.at(-1)?.seq ?? 0) + 1, itemId: id, op, data, base, sent: false });
    }
    await s.putItem<R>(app, { ...item, local: { data, deleted: op === 'delete' } });
  }

  /** Send the outbox, one entry per item per round, until it is empty or waits on nothing it can send. */
  async push(): Promise<{ pushed: number; conflicts: number }> {
    const { app, storage: s, transport: t } = this.o;
    let pushed = 0;
    let conflicts = 0;
    for (;;) {
      const seen = new Set<string>();
      const ready: OutboxEntry<R>[] = [];
      for (const e of await s.outbox<R>(app)) {
        if (!seen.has(e.itemId) && resolved(e.base) && ready.length < PUSH_MAX) ready.push(e);
        seen.add(e.itemId);
      }
      if (!ready.length) return { pushed, conflicts };
      for (const e of ready) if (!e.sent) await s.putEntry<R>(app, { ...e, sent: true }); // saved before it leaves
      const results = await t.push(app, ready.map((e) => ({
        key: e.key, item_id: e.itemId, op: e.op, base_version: e.base as number | null, data: e.data })));
      if (!results.some((r) => ready.some((e) => e.key === r.key))) throw new Error('the box answered none of the sent changes');
      for (const r of results) {
        const e = ready.find((x) => x.key === r.key);
        if (!e) continue;
        await s.removeEntry(app, e.key);
        pushed += 1;
        const conflict = r.status === 'conflict';
        if (conflict) conflicts += 1;
        // An entry made after this one edits from what this one did. After a conflict it keeps the old
        // base, so it becomes a conflict copy too: an edit made offline never overwrites a newer one.
        const rest = (await s.outbox<R>(app)).filter((w) => w.itemId === e.itemId);
        for (const w of rest) {
          if (!resolved(w.base) && w.base.after === e.key) await s.putEntry<R>(app, { ...w, base: conflict ? e.base : r.version });
        }
        const item = await s.getItem<R>(app, e.itemId);
        if (item && !rest.length) {
          const server = conflict ? item.server : {
            data: e.data, deleted: e.op === 'delete', version: r.version,
            conflictOf: item.server?.conflictOf ?? null, changedAt: item.server?.changedAt ?? null };
          await s.putItem<R>(app, { ...item, server, local: null });
        }
      }
    }
  }

  /** Read the feed from the saved cursor to its end. Applying a change twice is harmless. */
  async pull(): Promise<number> {
    const { app, storage: s, transport: t } = this.o;
    let pulled = 0;
    for (;;) {
      const { changes, more } = await t.pull(app, await s.getMeta(app, 'cursor'), PAGE);
      for (const c of changes) {
        const item = (await s.getItem<R>(app, c.item_id)) ?? { id: c.item_id, server: null, local: null };
        await s.putItem<R>(app, { ...item, server: {
          data: c.data, deleted: c.deleted, version: c.version, conflictOf: c.conflict_of, changedAt: c.changed_at } });
      }
      pulled += changes.length;
      const last = changes.at(-1);
      if (last) await s.setMeta(app, 'cursor', last.cursor);
      if (!more || !last) break;
    }
    await s.setMeta(app, 'pulled_at', String(this.now())); // every cached item is current as of now
    return pulled;
  }

  async sync(): Promise<SyncReport> {
    const p = await this.push();
    return { ...p, pulled: await this.pull(), attempts: 1 };
  }

  /** sync(), retried with exponential backoff while the box is unreachable or busy. */
  async syncWithBackoff(): Promise<SyncReport> {
    const { baseMs, maxMs, attempts } = this.o.backoff ?? { baseMs: 1000, maxMs: 60_000, attempts: 6 };
    const sleep = this.o.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
    for (let i = 1; ; i += 1) {
      try {
        return { ...(await this.sync()), attempts: i };
      } catch (e) {
        if (i >= attempts || !retryable(e)) throw e;
        await sleep(Math.min(maxMs, baseMs * 2 ** (i - 1)));
      }
    }
  }

  /** What a screen lists: live items, this device's unsent edits on top, each with its age. */
  async items(): Promise<ItemView<R>[]> {
    const { app, storage: s } = this.o;
    const at = await s.getMeta(app, 'pulled_at');
    const now = this.now();
    return (await s.listItems<R>(app))
      .filter((i) => !(i.local ? i.local.deleted : (i.server?.deleted ?? true)))
      .map((i) => ({
        id: i.id,
        data: i.local ? i.local.data : (i.server?.data ?? null),
        pending: i.local !== null,
        conflictOf: i.server?.conflictOf ?? null,
        version: i.server?.version ?? null,
        ageMs: i.server && at !== null ? now - Number(at) : null,
      }));
  }

  async pending(): Promise<number> { return (await this.o.storage.outbox(this.o.app)).length; }
}

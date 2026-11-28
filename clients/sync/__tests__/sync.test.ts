// SPDX-License-Identifier: Apache-2.0
// The OneMind Sync client kit against a box that follows docs/design/SYNC.md §4-§5 (the gateway's own
// rules are tested in core/tests/test_sync_reminders.py; e2e/two-devices.ts runs the kit on the real gateway).
import { MemoryStorage, SqliteStorage, SyncClient, SyncHttpError, type SqliteDb, type SyncStorage } from '../src/index.ts';
import type { Change, PushOp, PushResult, Transport } from '../src/types.ts';

type Reminder = { title: string; due_at?: string | null; done?: boolean };

/** The box's push and feed rules, in memory, with a switch for airplane mode and for lost answers. */
class Box implements Transport<Reminder> {
  log: Change<Reminder>[] = [];
  receipts = new Map<string, PushResult>();
  online = true;
  loseAnswers = 0;
  private gate() { if (!this.online) throw new TypeError('Network request failed'); }
  private head(id: string) { return this.log.filter((c) => c.item_id === id).pop(); }
  private write(id: string, version: number, op: PushOp<Reminder>, conflictOf: string | null = null) {
    const cursor = String(this.log.length + 1);
    const deleted = op.op === 'delete';
    this.log.push({ cursor, item_id: id, version, deleted, conflict_of: conflictOf, changed_at: '2026-11-11T22:00:00Z',
      data: deleted ? null : { ...op.data!, id, updated_at: '2026-11-11T22:00:00Z' } });
  }
  private apply(op: PushOp<Reminder>): PushResult {
    const cur = this.head(op.item_id);
    const r = { key: op.key, item_id: op.item_id, conflict_of: null, replayed: false };
    if (op.op === 'delete' && (!cur || cur.deleted)) return { ...r, status: 'applied', version: cur?.version ?? 0 };
    if (op.base_version === (cur?.version ?? null)) {
      this.write(op.item_id, (cur?.version ?? 0) + 1, op);
      return { ...r, status: 'applied', version: (cur?.version ?? 0) + 1 };
    }
    if (op.op === 'delete') return { ...r, status: 'conflict', version: cur!.version };
    const copy = `${op.item_id}-conflict-${op.key}`;
    this.write(copy, 1, op, op.item_id);
    return { ...r, status: 'conflict', item_id: copy, version: 1, conflict_of: op.item_id };
  }
  async push(_app: string, ops: PushOp<Reminder>[]) {
    this.gate();
    const out = ops.map((op) => {
      const seen = this.receipts.get(op.key);
      if (seen) return { ...seen, replayed: true };
      const r = this.apply(op);
      this.receipts.set(op.key, r);
      return r;
    });
    if (this.loseAnswers > 0) { this.loseAnswers -= 1; throw new TypeError('Network request failed'); } // applied, answer lost
    return out;
  }
  async pull(_app: string, cursor: string | null, limit: number) {
    this.gate();
    const rest = this.log.filter((c) => Number(c.cursor) > Number(cursor ?? 0));
    return { changes: rest.slice(0, limit), more: rest.length > limit };
  }
}

let clock = 1_000_000;
let n = 0;
function device(box: Box, storage: SyncStorage = new MemoryStorage(), slept: number[] = []) {
  return new SyncClient<Reminder>({ app: 'reminders', storage, transport: box, now: () => clock,
    newKey: () => `key-${String(++n).padStart(6, '0')}`, sleep: async (ms) => { slept.push(ms); },
    backoff: { baseMs: 1000, maxMs: 4000, attempts: 4 } });
}
const titles = async (d: SyncClient<Reminder>) => (await d.items()).map((i) => i.data?.title).sort();

function nodeSqlite(): SqliteDb { // a real SQLite (node:sqlite) behind the expo-sqlite method names
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const db = new (require('node:sqlite').DatabaseSync)(':memory:');
  return {
    execAsync: async (s) => { db.exec(s); },
    runAsync: async (s, ...p) => db.prepare(s).run(...p),
    getFirstAsync: async (s, ...p) => db.prepare(s).get(...p) ?? null,
    getAllAsync: async (s, ...p) => db.prepare(s).all(...p),
  };
}

describe.each([['memory', () => new MemoryStorage()], ['sqlite', () => new SqliteStorage(nodeSqlite())]])('%s storage', (_, store) => {
  test('airplane mode: changes queue on the device, then go once the box is back', async () => {
    const box = new Box();
    const slept: number[] = [];
    const phone = device(box, store(), slept);
    box.online = false;
    await phone.save('r1', { title: 'Buy milk' });
    await phone.save('r1', { title: 'Buy oat milk' }); // folded into the unsent change
    await phone.save('r2', { title: 'Call Ana', due_at: '2026-11-12T09:00:00Z' });
    await phone.save('r3', { title: 'Typo' });
    await phone.remove('r3');
    expect(await phone.pending()).toBe(3);
    expect(await titles(phone)).toEqual(['Buy oat milk', 'Call Ana']);
    expect((await phone.items()).every((i) => i.pending && i.ageMs === null)).toBe(true);
    await expect(phone.syncWithBackoff()).rejects.toThrow('Network request failed');
    expect(slept).toEqual([1000, 2000, 4000]);
    expect(await phone.pending()).toBe(3);

    box.online = true;
    const report = await phone.syncWithBackoff();
    expect(report).toEqual({ pushed: 3, conflicts: 0, pulled: 2, attempts: 1 });
    expect(box.log.map((c) => [c.item_id, c.version, c.data?.title])).toEqual([['r1', 1, 'Buy oat milk'], ['r2', 1, 'Call Ana']]);
    expect(await phone.pending()).toBe(0);
    clock += 90_000;
    expect((await phone.items()).map((i) => [i.data?.title, i.pending, i.ageMs])).toEqual([
      ['Buy oat milk', false, 90_000], ['Call Ana', false, 90_000]]);
  });

  test('reconnect: an answer lost on the way back is sent again and applied exactly once', async () => {
    const box = new Box();
    const phone = device(box, store());
    await phone.save('r1', { title: 'Buy milk' });
    box.loseAnswers = 1;
    await expect(phone.sync()).rejects.toThrow();
    await phone.save('r1', { title: 'Buy milk', done: true }); // made while the first is unconfirmed
    const report = await phone.syncWithBackoff();
    expect(report.pushed).toBe(2);
    expect(box.log.map((c) => [c.item_id, c.version, c.data?.done])).toEqual([['r1', 1, undefined], ['r1', 2, true]]);
    box.loseAnswers = 1; // the whole sync fails once more, the retry replays nothing new
    await phone.save('r2', { title: 'Call Ana' });
    expect((await phone.syncWithBackoff()).attempts).toBe(2);
    expect(box.log.filter((c) => c.item_id === 'r2')).toHaveLength(1);
    expect(await phone.pending()).toBe(0);
  });

  test('conflict: two devices edit the same reminder offline and both copies survive on both', async () => {
    const box = new Box();
    const phone = device(box, store());
    const laptop = device(box, store());
    await phone.save('r1', { title: 'Buy milk' });
    await phone.sync();
    await laptop.sync();
    await phone.save('r1', { title: 'Buy oat milk' });
    await laptop.save('r1', { title: 'Buy milk and eggs' });
    await laptop.remove('r1-gone'); // deleting something the box never had is harmless
    expect((await phone.sync()).conflicts).toBe(0);
    expect((await laptop.sync()).conflicts).toBe(1);
    await phone.sync();
    for (const d of [phone, laptop]) {
      expect(await titles(d)).toEqual(['Buy milk and eggs', 'Buy oat milk']);
      const copy = (await d.items()).find((i) => i.conflictOf === 'r1');
      expect(copy?.data?.title).toBe('Buy milk and eggs');
    }
    // Both create r9 offline; the laptop's create lands as a copy (answer lost), then it edits r9 again:
    // that edit follows the copy's fate and never overwrites the phone's r9.
    await phone.save('r9', { title: 'Phone r9' });
    await laptop.save('r9', { title: 'Laptop r9' });
    await phone.sync();
    box.loseAnswers = 1;
    await expect(laptop.sync()).rejects.toThrow();
    await laptop.save('r9', { title: 'Laptop r9, edited' });
    await laptop.sync();
    expect(box.log.filter((c) => c.item_id === 'r9').map((c) => c.data?.title)).toEqual(['Phone r9']);
    expect(box.log.filter((c) => c.conflict_of === 'r9').map((c) => c.data?.title)).toEqual(['Laptop r9', 'Laptop r9, edited']);
    // A stale delete never removes the newer edit.
    await laptop.sync();
    await phone.save('r1', { title: 'Buy oat milk!' });
    await laptop.remove('r1');
    await phone.sync();
    expect((await laptop.sync()).conflicts).toBe(1);
    expect(await titles(laptop)).toEqual(['Buy milk and eggs', 'Buy oat milk!', 'Laptop r9', 'Laptop r9, edited', 'Phone r9']);
  });
});

test('a refusal from the box is not retried', async () => {
  const slept: number[] = [];
  const box = new Box();
  box.push = async () => { throw new SyncHttpError(409, 'app_disabled', 'Reminders is switched off'); };
  const phone = device(box, new MemoryStorage(), slept);
  await phone.save('r1', { title: 'x' });
  await expect(phone.syncWithBackoff()).rejects.toMatchObject({ status: 409, reason: 'app_disabled' });
  expect(slept).toEqual([]);
  expect(await phone.pending()).toBe(1);
});

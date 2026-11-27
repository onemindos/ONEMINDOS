// SPDX-License-Identifier: Apache-2.0
// Where the kit keeps the cache, the cursor and the outbox. MemoryStorage is for tests and the web
// before IndexedDB; SqliteStorage takes an expo-sqlite database handle (mobile, issue #1290).
import type { CachedItem, OutboxEntry } from './types.ts';

export interface SyncStorage {
  getMeta(app: string, key: string): Promise<string | null>;
  setMeta(app: string, key: string, value: string): Promise<void>;
  getItem<R>(app: string, id: string): Promise<CachedItem<R> | null>;
  putItem<R>(app: string, item: CachedItem<R>): Promise<void>;
  listItems<R>(app: string): Promise<CachedItem<R>[]>;
  outbox<R>(app: string): Promise<OutboxEntry<R>[]>; // in seq order
  putEntry<R>(app: string, entry: OutboxEntry<R>): Promise<void>; // insert or replace by key
  removeEntry(app: string, key: string): Promise<void>;
}

const copy = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T; // like a real store: no shared objects

export class MemoryStorage implements SyncStorage {
  private meta = new Map<string, string>();
  private items = new Map<string, Map<string, unknown>>();
  private box = new Map<string, Map<string, unknown>>();
  private of(m: Map<string, Map<string, unknown>>, app: string): Map<string, unknown> {
    if (!m.has(app)) m.set(app, new Map());
    return m.get(app)!;
  }
  async getMeta(app: string, key: string) { return this.meta.get(`${app}/${key}`) ?? null; }
  async setMeta(app: string, key: string, value: string) { this.meta.set(`${app}/${key}`, value); }
  async getItem<R>(app: string, id: string) { const v = this.of(this.items, app).get(id); return v ? copy(v as CachedItem<R>) : null; }
  async putItem<R>(app: string, item: CachedItem<R>) { this.of(this.items, app).set(item.id, copy(item)); }
  async listItems<R>(app: string) { return [...this.of(this.items, app).values()].map((v) => copy(v as CachedItem<R>)); }
  async outbox<R>(app: string) {
    return [...this.of(this.box, app).values()].map((v) => copy(v as OutboxEntry<R>)).sort((a, b) => a.seq - b.seq);
  }
  async putEntry<R>(app: string, entry: OutboxEntry<R>) { this.of(this.box, app).set(entry.key, copy(entry)); }
  async removeEntry(app: string, key: string) { this.of(this.box, app).delete(key); }
}

/** The part of expo-sqlite's SQLiteDatabase the kit uses (expo-sqlite 58, packages/expo-sqlite/src/SQLiteDatabase.ts). */
export interface SqliteDb {
  execAsync(source: string): Promise<void>;
  runAsync(source: string, ...params: (string | number | null)[]): Promise<unknown>;
  getFirstAsync<T>(source: string, ...params: (string | number | null)[]): Promise<T | null>;
  getAllAsync<T>(source: string, ...params: (string | number | null)[]): Promise<T[]>;
}

const TABLES = `
CREATE TABLE IF NOT EXISTS onemind_sync_meta (app TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL, PRIMARY KEY (app, k));
CREATE TABLE IF NOT EXISTS onemind_sync_items (app TEXT NOT NULL, id TEXT NOT NULL, doc TEXT NOT NULL, PRIMARY KEY (app, id));
CREATE TABLE IF NOT EXISTS onemind_sync_outbox (app TEXT NOT NULL, key TEXT NOT NULL, seq INTEGER NOT NULL, doc TEXT NOT NULL, PRIMARY KEY (app, key));`;

export class SqliteStorage implements SyncStorage {
  private ready: Promise<void> | null = null;
  private db: SqliteDb;
  constructor(db: SqliteDb) { this.db = db; }
  private async q(): Promise<SqliteDb> { await (this.ready ??= this.db.execAsync(TABLES)); return this.db; }
  async getMeta(app: string, key: string) {
    const r = await (await this.q()).getFirstAsync<{ v: string }>('SELECT v FROM onemind_sync_meta WHERE app = ? AND k = ?', app, key);
    return r ? r.v : null;
  }
  async setMeta(app: string, key: string, value: string) {
    await (await this.q()).runAsync('INSERT OR REPLACE INTO onemind_sync_meta (app, k, v) VALUES (?, ?, ?)', app, key, value);
  }
  async getItem<R>(app: string, id: string) {
    const r = await (await this.q()).getFirstAsync<{ doc: string }>('SELECT doc FROM onemind_sync_items WHERE app = ? AND id = ?', app, id);
    return r ? (JSON.parse(r.doc) as CachedItem<R>) : null;
  }
  async putItem<R>(app: string, item: CachedItem<R>) {
    await (await this.q()).runAsync('INSERT OR REPLACE INTO onemind_sync_items (app, id, doc) VALUES (?, ?, ?)', app, item.id, JSON.stringify(item));
  }
  async listItems<R>(app: string) {
    const rows = await (await this.q()).getAllAsync<{ doc: string }>('SELECT doc FROM onemind_sync_items WHERE app = ? ORDER BY id', app);
    return rows.map((r) => JSON.parse(r.doc) as CachedItem<R>);
  }
  async outbox<R>(app: string) {
    const rows = await (await this.q()).getAllAsync<{ doc: string }>('SELECT doc FROM onemind_sync_outbox WHERE app = ? ORDER BY seq', app);
    return rows.map((r) => JSON.parse(r.doc) as OutboxEntry<R>);
  }
  async putEntry<R>(app: string, e: OutboxEntry<R>) {
    await (await this.q()).runAsync('INSERT OR REPLACE INTO onemind_sync_outbox (app, key, seq, doc) VALUES (?, ?, ?, ?)', app, e.key, e.seq, JSON.stringify(e));
  }
  async removeEntry(app: string, key: string) {
    await (await this.q()).runAsync('DELETE FROM onemind_sync_outbox WHERE app = ? AND key = ?', app, key);
  }
}

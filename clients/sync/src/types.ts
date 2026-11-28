// SPDX-License-Identifier: Apache-2.0
// OneMind Sync (F1) wire and cache types. The wire shapes follow docs/design/SYNC.md; the app's
// record type R comes from @onemind/sdk once a screen uses the kit (spike: the kit stays generic).

export type Op = 'upsert' | 'delete';

/** One entry of GET /v1/sync/<app>/changes. */
export interface Change<R> {
  cursor: string;
  item_id: string;
  version: number;
  deleted: boolean;
  conflict_of: string | null;
  changed_at: string;
  data: (R & { id: string; updated_at: string }) | null;
}

export interface PushOp<R> { key: string; item_id: string; op: Op; base_version: number | null; data: R | null }

export interface PushResult {
  key: string;
  status: 'applied' | 'conflict';
  item_id: string;
  version: number | null;
  conflict_of: string | null;
  replayed: boolean;
}

export interface Transport<R> {
  pull(app: string, cursor: string | null, limit: number): Promise<{ changes: Change<R>[]; more: boolean }>;
  push(app: string, ops: PushOp<R>[]): Promise<PushResult[]>;
}

/** The base an outbox entry was edited from: a server version, null (new item), or "after my earlier entry". */
export type Base = number | null | { after: string };

export interface OutboxEntry<R> {
  key: string; // idempotency key, fixed when the person makes the change
  seq: number; // order in the outbox
  itemId: string;
  op: Op;
  data: R | null;
  base: Base;
  sent: boolean; // true once it may have reached the box: never folded into again
}

export interface ServerState<R> {
  data: R | null;
  deleted: boolean;
  version: number | null;
  conflictOf: string | null;
  changedAt: string | null;
}

/** What the device keeps per item: the box's last known state, plus this device's unsent change. */
export interface CachedItem<R> {
  id: string;
  server: ServerState<R> | null;
  local: { data: R | null; deleted: boolean } | null;
}

/** What a screen shows. ageMs: how old the box's copy is (null: never on the box yet). */
export interface ItemView<R> {
  id: string;
  data: R | null;
  pending: boolean;
  conflictOf: string | null;
  version: number | null;
  ageMs: number | null;
}

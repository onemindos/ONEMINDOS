// SPDX-License-Identifier: Apache-2.0
import type { OneMindApi } from './client';
import { MockWiringBase } from './mockWiring';
import { installBlockReason } from '../lib/scan';
import { DEMO_TOKENS, INSTANCE, makeActions, makeApps, makeNodes } from './fixtures';
import { ApiError, type Action, type ActionRequest, type CatalogApp, type Principal } from './types';

/**
 * In-memory stand-in for the gateway (VITE_MOCK=1). It follows the §3 rules that
 * matter for the UI: unknown token → 401, only owner/agent may request, only
 * the owner may approve or deny, the idempotency key returns the same action,
 * approving after expires_at → 409 expired, approving an install without a fresh
 * passing scan → 409 stale_precondition (§10.3). Approval runs the `noop` executor
 * path (accepted → dispatched → succeeded), one step every `stepMs`, applied on the next read, so
 * the dashboard's live progress can be seen in the demo. `stepMs: 0` finishes on the next read.
 */
export class MockApi extends MockWiringBase implements OneMindApi {
  protected readonly principal: Principal | undefined;
  protected readonly now: () => number;
  private catalog: CatalogApp[];
  private actionsList: Action[];
  private seq = 2;
  private readonly stepMs: number;
  /** When each approved action was accepted (mock clock, ms). */
  private readonly acceptedAt = new Map<string, number>();

  constructor(token: string, opts: { now?: () => number; stepMs?: number } = {}) {
    super();
    this.principal = DEMO_TOKENS[token];
    this.now = opts.now ?? (() => Date.now());
    this.stepMs = opts.stepMs ?? 0;
    this.catalog = makeApps(this.now());
    this.actionsList = makeActions(this.now());
  }

  protected auth(): Principal {
    if (!this.principal) throw new ApiError(401, 'unauthenticated', 'Unknown token');
    return this.principal;
  }

  private find(id: string): Action {
    const a = this.actionsList.find((x) => x.id === id);
    if (!a) throw new ApiError(404, 'not_found', `No action ${id}`);
    this.advance(a);
    return a;
  }

  /** The noop executor's steps, by elapsed mock time since approval. */
  private advance(a: Action) {
    const at = this.acceptedAt.get(a.id);
    if (at === undefined) return;
    const steps = this.stepMs <= 0 ? 2 : Math.floor((this.now() - at) / this.stepMs);
    const next = steps >= 2 ? 'succeeded' : steps >= 1 ? 'dispatched' : 'accepted';
    if (next === a.state) return;
    a.state = next;
    a.updated_at = new Date(this.now()).toISOString();
    if (next !== 'succeeded') return;
    this.acceptedAt.delete(a.id);
    a.result = { outcome: 'succeeded', message: 'noop executor', steps: [] };
    this.catalog = this.catalog.map((app) =>
      app.id === a.params.app_id
        ? { ...app, installed: a.type === 'app.install', status: a.type === 'app.install' ? 'installed' : 'not_installed' }
        : app,
    );
  }

  /** An alert fix is only ever a request: awaiting approval, requested by the caller. */
  protected fileAction(type: string, params: Record<string, unknown>): Action {
    const p = this.auth();
    const key = `fix:${type}:${JSON.stringify(params)}:${p.id}`;
    const existing = this.actionsList.find((a) => a.idempotency_key === key);
    if (existing) return { ...existing };
    const ts = new Date(this.now()).toISOString();
    const action: Action = {
      id: `act-${String(this.seq++).padStart(4, '0')}`,
      type: type as Action['type'],
      params: params as Action['params'],
      idempotency_key: key,
      expires_at: new Date(this.now() + 86_400_000).toISOString(),
      state: 'awaiting_approval',
      requested_by: p,
      created_at: ts,
      updated_at: ts,
    };
    this.actionsList = [action, ...this.actionsList];
    return { ...action };
  }

  private ownerOnly(): Principal {
    const p = this.auth();
    if (p.role !== 'owner') throw new ApiError(403, 'permission_denied', 'Only the owner can decide on actions');
    return p;
  }

  hubOffsetMs() {
    return this.now() - Date.now();
  }
  async healthz() {
    return { ok: true };
  }
  async instance() {
    this.auth();
    return { ...INSTANCE };
  }
  async nodes() {
    this.auth();
    return makeNodes(this.now());
  }
  async node(nodeId: string) {
    this.auth();
    const n = makeNodes(this.now()).find((x) => x.node_id === nodeId);
    if (!n) throw new ApiError(404, 'not_found', `No node ${nodeId}`);
    return n;
  }
  async apps() {
    this.auth();
    this.actionsList.forEach((a) => this.advance(a));
    return this.catalog.map((a) => ({ ...a }));
  }
  async createAction(req: ActionRequest) {
    const p = this.auth();
    if (p.role !== 'owner' && p.kind !== 'agent') {
      throw new ApiError(403, 'permission_denied', 'Only the owner or an agent can request actions');
    }
    const existing = this.actionsList.find((a) => a.idempotency_key === req.idempotency_key);
    if (existing) return { ...existing };
    const ts = new Date(this.now()).toISOString();
    const action: Action = {
      ...req,
      id: `act-${String(this.seq++).padStart(4, '0')}`,
      state: 'awaiting_approval',
      requested_by: p,
      created_at: ts,
      updated_at: ts,
    };
    this.actionsList = [action, ...this.actionsList];
    return { ...action };
  }
  async actions() {
    this.auth();
    this.actionsList.forEach((a) => this.advance(a));
    return this.actionsList.map((a) => ({ ...a }));
  }
  async action(id: string) {
    this.auth();
    return { ...this.find(id) };
  }
  async approve(id: string) {
    const p = this.ownerOnly();
    const a = this.find(id);
    if (a.state !== 'awaiting_approval') throw new ApiError(409, 'conflict', `Action is ${a.state}`);
    if (Date.parse(a.expires_at) <= this.now()) {
      a.state = 'expired';
      throw new ApiError(409, 'expired', 'The approval window has passed');
    }
    const app = this.catalog.find((x) => x.id === a.params.app_id);
    const blocked = a.type === 'app.install' && app ? installBlockReason(app, this.now()) : undefined;
    if (blocked) throw new ApiError(409, 'stale_precondition', blocked);
    const ts = this.now();
    a.state = 'accepted';
    a.decided_by = p;
    a.decided_at = new Date(ts).toISOString();
    a.updated_at = a.decided_at;
    this.acceptedAt.set(a.id, ts);
    this.advance(a);
    return { ...a };
  }
  async deny(id: string) {
    const p = this.ownerOnly();
    const a = this.find(id);
    if (a.state !== 'awaiting_approval') throw new ApiError(409, 'conflict', `Action is ${a.state}`);
    a.state = 'cancelled';
    a.decided_by = p;
    a.decided_at = new Date(this.now()).toISOString();
    a.updated_at = new Date(this.now()).toISOString();
    return { ...a };
  }
}

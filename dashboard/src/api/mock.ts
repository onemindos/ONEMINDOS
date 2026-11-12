import type { OneMindApi } from './client';
import { installBlockReason } from '../lib/scan';
import { DEMO_TOKENS, INSTANCE, makeActions, makeApps, makeNodes } from './fixtures';
import { ApiError, type Action, type ActionRequest, type CatalogApp, type Principal } from './types';

/**
 * In-memory stand-in for the gateway (VITE_MOCK=1). It follows the §3 rules that
 * matter for the UI: unknown token → 401, only owner/agent may request, only
 * the owner may approve or deny, the idempotency key returns the same action,
 * approving after expires_at → 409 expired, approving an install without a fresh
 * passing scan → 409 stale_precondition (§10.3). Approval runs the `noop` executor
 * path (accepted → dispatched → succeeded) instantly.
 */
export class MockApi implements OneMindApi {
  private readonly principal: Principal | undefined;
  private readonly now: () => number;
  private catalog: CatalogApp[];
  private actionsList: Action[];
  private seq = 2;

  constructor(token: string, opts: { now?: () => number } = {}) {
    this.principal = DEMO_TOKENS[token];
    this.now = opts.now ?? (() => Date.now());
    this.catalog = makeApps(this.now());
    this.actionsList = makeActions(this.now());
  }

  private auth(): Principal {
    if (!this.principal) throw new ApiError(401, 'unauthenticated', 'Unknown token');
    return this.principal;
  }

  private find(id: string): Action {
    const a = this.actionsList.find((x) => x.id === id);
    if (!a) throw new ApiError(404, 'not_found', `No action ${id}`);
    return a;
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
    a.state = 'succeeded';
    a.result = { outcome: 'succeeded', message: 'noop executor', steps: [] };
    a.decided_by = p;
    a.updated_at = new Date(this.now()).toISOString();
    this.catalog = this.catalog.map((app) =>
      app.id === a.params.app_id
        ? { ...app, installed: a.type === 'app.install', status: a.type === 'app.install' ? 'installed' : 'not_installed' }
        : app,
    );
    return { ...a };
  }
  async deny(id: string) {
    const p = this.ownerOnly();
    const a = this.find(id);
    if (a.state !== 'awaiting_approval') throw new ApiError(409, 'conflict', `Action is ${a.state}`);
    a.state = 'cancelled';
    a.decided_by = p;
    a.updated_at = new Date(this.now()).toISOString();
    return { ...a };
  }
}

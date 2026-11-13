// SPDX-License-Identifier: Apache-2.0
// Copied from dashboard/src/api/mock.ts (feat/gwmcp, commit 951470f) so the phone app and the
// dashboard speak the same contract types. Keep the two in sync; mobile changes noted inline.
import { Features, OP, type OneMindApi } from './client';
import { installBlockReason } from '../lib/scan';
import { DEMO_TOKENS, INSTANCE, makeActions, makeAlerts, makeApps, makeInbox, makeNodes } from './fixtures';
import {
  ApiError,
  type Action,
  type ActionRequest,
  type AlertRecord,
  type ApproveBody,
  type CatalogApp,
  type InboxItem,
  type Me,
  type Principal,
} from './types';

/**
 * Mobile addition: the §12 routes the demo serves. No passkeys, push, devices or event stream: those need a
 * real authenticator, a push service and a network, and the demo never talks to one.
 */
export const DEMO_FEATURES = [OP.me, OP.approveOptions, OP.preview, OP.notifications, OP.alerts];

const unsupported = (what: string) => () => Promise.reject(new ApiError(404, 'not_found', `${what} is not part of the demo`));

/**
 * In-memory stand-in for the gateway (mock mode: the "Try the demo" button). It follows the §3 rules that
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
  private inbox: InboxItem[];
  private alertList: AlertRecord[];
  private seq = 2;

  constructor(token: string, opts: { now?: () => number } = {}) {
    this.principal = DEMO_TOKENS[token];
    this.now = opts.now ?? (() => Date.now());
    this.catalog = makeApps(this.now());
    this.actionsList = makeActions(this.now());
    this.inbox = this.principal?.kind === 'person' ? makeInbox(this.now(), this.principal.id) : [];
    this.alertList = this.principal?.role === 'owner' ? makeAlerts(this.now()) : [];
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
  async approve(id: string, body?: ApproveBody) {
    const p = this.ownerOnly();
    const a = this.find(id);
    if (a.state !== 'awaiting_approval') throw new ApiError(409, 'conflict', `Action is ${a.state}`);
    // §12.4: the approval is bound to the plan the owner saw.
    if (body?.plan_sha256 && a.plan_sha256 && body.plan_sha256 !== a.plan_sha256)
      throw new ApiError(409, 'stale_precondition', 'the plan changed since the request', { reason: 'plan_changed' });
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
    a.approved_by = `${p.kind}:${p.id}`;
    a.approved_via = 'phone';
    a.approval = body?.webauthn ? 'passkey' : 'token';
    a.updated_at = new Date(this.now()).toISOString();
    this.catalog = this.catalog.map((app) =>
      app.id === a.params.app_id
        ? { ...app, installed: a.type === 'app.install', status: a.type === 'app.install' ? 'installed' : 'not_installed' }
        : app,
    );
    return { ...a };
  }
  async deny(id: string, reason?: string) {
    const p = this.ownerOnly();
    const a = this.find(id);
    if (a.state !== 'awaiting_approval') throw new ApiError(409, 'conflict', `Action is ${a.state}`);
    a.state = 'cancelled';
    a.decided_by = p;
    a.updated_at = new Date(this.now()).toISOString();
    if (reason) a.result = { outcome: 'denied', message: reason };
    return { ...a };
  }

  // Mobile additions: the §12 routes in DEMO_FEATURES.
  async features() {
    return new Features(DEMO_FEATURES, 'demo');
  }
  async me(): Promise<Me> {
    const p = this.auth();
    const capabilities = [
      ...(p.role === 'owner' ? ['can_approve'] : []),
      ...(p.role === 'owner' || p.kind === 'agent' ? ['can_request'] : []),
    ];
    return { principal: { ...p }, token: { id: `tok_demo_${p.id}`, scopes: [], expires_at: null }, session: null, passkeys: 0, capabilities };
  }
  async approveOptions(id: string) {
    this.ownerOnly();
    const a = this.find(id);
    return {
      challenge: 'ZGVtby1jaGFsbGVuZ2U',
      action_sha256: 'sha256:demo',
      plan_sha256: a.plan_sha256 ?? 'sha256:demo-plan',
      expires_at: new Date(this.now() + 120_000).toISOString(),
    };
  }
  async preview(id: string) {
    this.auth();
    const a = this.find(id);
    return { plan: a.plan ?? {}, plan_sha256: a.plan_sha256 ?? 'sha256:demo-plan' };
  }
  private person(): Principal {
    const p = this.auth();
    if (p.kind !== 'person') throw new ApiError(403, 'permission_denied', 'Only people have an inbox');
    return p;
  }
  async notifications(q: { unread?: boolean } = {}) {
    this.person();
    return this.inbox.filter((n) => !q.unread || !n.read_at).map((n) => ({ ...n }));
  }
  async notification(id: string) {
    this.person();
    const n = this.inbox.find((x) => x.id === id);
    if (!n) throw new ApiError(404, 'not_found', `No notification ${id}`);
    return { ...n };
  }
  async markRead(id: string) {
    this.person();
    this.inbox = this.inbox.map((n) => (n.id === id && !n.read_at ? { ...n, read_at: new Date(this.now()).toISOString() } : n));
  }
  async markAllRead() {
    this.person();
    const marked = this.inbox.filter((n) => !n.read_at).length;
    const ts = new Date(this.now()).toISOString();
    this.inbox = this.inbox.map((n) => (n.read_at ? n : { ...n, read_at: ts }));
    return { marked };
  }
  async alerts(state?: 'open') {
    this.auth();
    return this.alertList.filter((a) => !state || a.state === state).map((a) => ({ ...a }));
  }
  async ackAlert(id: string) {
    const p = this.auth();
    if (p.role !== 'owner' && p.role !== 'adult') throw new ApiError(403, 'permission_denied', 'Only owners and adults acknowledge alerts');
    const a = this.alertList.find((x) => x.id === id);
    if (!a) throw new ApiError(404, 'not_found', `No alert ${id}`);
    a.state = 'acknowledged';
    return { ...a };
  }
  async fixAlert(id: string) {
    const a = this.alertList.find((x) => x.id === id);
    if (!a?.fix) throw new ApiError(404, 'not_found', `Alert ${id} has no fix`);
    const p = this.auth();
    if (p.role !== 'owner' && p.kind !== 'agent') throw new ApiError(403, 'permission_denied', 'Only an owner or an agent can file a fix');
    const ts = new Date(this.now()).toISOString();
    const action: Action = {
      id: `act-${String(this.seq++).padStart(4, '0')}`,
      type: a.fix.type,
      params: a.fix.params,
      idempotency_key: `fix-${id}`,
      expires_at: new Date(this.now() + 24 * 3600_000).toISOString(),
      state: 'awaiting_approval',
      requested_by: p,
      risk: 'write',
      created_at: ts,
      updated_at: ts,
    };
    this.actionsList = [action, ...this.actionsList];
    return { ...action };
  }
  // The demo has no first-run settings, lifecycle plans, backups, automation, files or migration.
  onboardingSettings = unsupported('First-run settings');
  saveOnboardingSettings = unsupported('First-run settings');
  appPlan = unsupported('Plans');
  backupStatus = unsupported('Backups');
  backupDestinations = unsupported('Backups');
  backupRuns = unsupported('Backups');
  requestBackupRun = unsupported('Backups');
  requestBackupVerify = unsupported('Backups');
  automationState = unsupported('Automation');
  automationRules = unsupported('Automation');
  automationRuns = unsupported('Automation');
  setRuleEnabled = unsupported('Automation');
  setAutomationPaused = unsupported('Automation');
  filesRoots = unsupported('Files');
  filesList = unsupported('Files');
  migratePlans = unsupported('Migration');
  pushRegister = unsupported('Push');
  pushRegistrations = unsupported('Push');
  pushUnregister = unsupported('Push');
  vapidPublicKey = unsupported('Push');
  loginOptions = unsupported('Passkey sign-in');
  login = unsupported('Passkey sign-in');
  refreshSession = unsupported('Sign-in');
  logout = async () => undefined;
  passkeyRegisterOptions = unsupported('Passkeys');
  passkeyRegister = unsupported('Passkeys');
  deviceRequest = unsupported('Device registration');
  deviceRequestStatus = unsupported('Device registration');
  deviceToken = unsupported('Device registration');
  eventsEndpoint() {
    return undefined;
  }
}

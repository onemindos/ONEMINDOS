// SPDX-License-Identifier: Apache-2.0
// Mock-mode stand-in for the §12 routes (VITE_MOCK=1 and the unit tests). It keeps the rules the
// UI depends on: owner-only people and tokens (403 otherwise), one-time secrets returned once,
// the last owner cannot be disabled, an alert fix is only ever a REQUEST (never approved here),
// bad credentials answer 401. All data is made up.
import { ApiError, type Action, type Principal } from './types';
import type * as W from './wiring';

const DEMO_PASSWORD = 'demo-password';
export const MOCK_SETUP_TOKEN = 'setup-demo';
export const MOCK_ENROL_CODE = 'enrol-demo';
const PERSONS: Record<string, { token: string; principal: W.PrincipalInfo }> = {
  owner: { token: 'owner-demo', principal: { id: 'owner', kind: 'person', role: 'owner', display_name: 'Owner', username: 'owner' } },
  alex: { token: 'adult-demo', principal: { id: 'alex', kind: 'person', role: 'adult', display_name: 'Alex', username: 'alex' } },
};

const hex = (seed: string) => {
  let h = 2166136261;
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return h.toString(16).padStart(8, '0').repeat(8);
};

export abstract class MockWiringBase implements W.WiringApi {
  protected abstract readonly principal: Principal | undefined;
  protected abstract readonly now: () => number;
  protected abstract auth(): Principal;
  /** Files an action as the caller, awaiting approval (never approved here). */
  protected abstract fileAction(type: string, params: Record<string, unknown>): Action;

  private setupDone = false;
  private sessionRows: W.SessionInfo[] | undefined;
  private passkeyRows: W.PasskeyInfo[] = [];
  private userRows: W.UserInfo[] | undefined;
  private tokenRows: W.TokenInfo[] | undefined;
  private notes: W.NotificationItem[] | undefined;
  private channelRows: W.ChannelInfo[] = [];
  private alertRows: W.AlertInfo[] | undefined;
  private wseq = 1;

  private iso(secondsAgo = 0) {
    return new Date(this.now() - secondsAgo * 1000).toISOString();
  }
  private id(p: string) {
    return `${p}_${String(this.wseq++).padStart(4, '0')}`;
  }
  private owner(): Principal {
    const p = this.auth();
    if (p.role !== 'owner') throw new ApiError(403, 'permission_denied', 'Only the owner can do this');
    return p;
  }
  private person(): Principal {
    const p = this.auth();
    if (p.kind !== 'person') throw new ApiError(403, 'permission_denied', 'Only people have an inbox and channels');
    return p;
  }
  private result(key: string): W.LoginResult {
    const e = PERSONS[key]!;
    return { access_token: e.token, expires_at: this.iso(-3600), principal: e.principal, session: { id: 'ses_mock', expires_at: this.iso(-86400) } };
  }

  // ---- sign-in ----------------------------------------------------------------------------------
  async loginOptions(): Promise<W.WebAuthnOptions> {
    return { challenge_id: 'chl_mock', expires_at: this.iso(-300), publicKey: { challenge: 'AAAA', rpId: 'localhost', timeout: 60000 } };
  }
  async loginPassword(b: { username: string; password: string; totp?: string }) {
    if (!PERSONS[b.username] || b.password !== DEMO_PASSWORD) throw new ApiError(401, 'unauthenticated', 'wrong username or password');
    return this.result(b.username);
  }
  async loginPasskey(c: Record<string, unknown>) {
    if (c.id !== 'demo-passkey') throw new ApiError(401, 'unauthenticated', 'unknown passkey');
    return this.result('owner');
  }
  async setup(setupToken: string, b: { username: string; display_name: string; password: string }) {
    if (setupToken !== MOCK_SETUP_TOKEN) throw new ApiError(401, 'unauthenticated', 'setup needs the install owner token or the first-boot token');
    if (this.setupDone) throw new ApiError(409, 'conflict', 'this box already has accounts; sign in instead', 'already_set_up');
    if (b.password.length < 12) throw new ApiError(422, 'conflict', 'password must be at least 12 characters');
    this.setupDone = true;
    return this.result('owner');
  }
  async enrol(b: { code: string; username?: string; password: string }) {
    if (b.code !== MOCK_ENROL_CODE) throw new ApiError(401, 'unauthenticated', 'that code is not valid');
    return this.result('alex');
  }

  // ---- the signed-in person ---------------------------------------------------------------------
  async me(): Promise<W.Me> {
    const p = this.auth();
    const caps = p.role === 'owner' ? ['can_approve', 'can_request', 'can_manage_users', 'can_share_apps', 'can_create_tokens'] : p.kind === 'agent' ? ['can_request'] : ['can_create_tokens'];
    return {
      principal: { id: p.id, kind: p.kind, role: p.role },
      token: { id: 'tok_mock', scopes: ['*'], expires_at: null, source: 'file' },
      session: null,
      passkeys: this.passkeyRows.length,
      scopes: ['*'],
      capabilities: caps,
      step_up: { passkeys_active: this.passkeyRows.length > 0, require_passkey_approval: false },
    };
  }
  async logout() {
    this.auth();
  }
  async sessions() {
    this.person();
    this.sessionRows ??= [
      { id: 'ses_mock', principal_id: this.principal!.id, client: 'dashboard on a laptop', transport: 'bearer', auth_method: 'password', created_at: this.iso(3600), last_seen_at: this.iso(5), expires_at: this.iso(-86400), current: true },
      { id: 'ses_phone', principal_id: this.principal!.id, client: 'phone browser', transport: 'bearer', auth_method: 'passkey', created_at: this.iso(86400), last_seen_at: this.iso(7200), expires_at: this.iso(-86400), current: false },
    ];
    return this.sessionRows.map((s) => ({ ...s }));
  }
  async revokeSession(id: string) {
    await this.sessions();
    if (!this.sessionRows!.some((s) => s.id === id)) throw new ApiError(404, 'not_found', 'no such session');
    this.sessionRows = this.sessionRows!.filter((s) => s.id !== id);
  }
  async passkeys() {
    this.person();
    return this.passkeyRows.map((p) => ({ ...p }));
  }
  async passkeyRegisterOptions() {
    this.person();
    return this.loginOptions();
  }
  async passkeyRegister(credential: Record<string, unknown>, label?: string) {
    this.person();
    const row: W.PasskeyInfo = { credential_id: String(credential.id ?? this.id('cred')), label: label ?? null, created_at: this.iso(), last_used_at: null };
    this.passkeyRows = [...this.passkeyRows, row];
    return row;
  }
  async deletePasskey(id: string) {
    this.person();
    if (!this.passkeyRows.some((p) => p.credential_id === id)) throw new ApiError(404, 'not_found', 'no such passkey');
    this.passkeyRows = this.passkeyRows.filter((p) => p.credential_id !== id);
  }

  // ---- people and tokens -------------------------------------------------------------------------
  private users_() {
    return (this.userRows ??= [
      { id: 'owner', username: 'owner', display_name: 'Owner', role: 'owner', created_at: this.iso(86400 * 30), last_seen_at: this.iso(60), disabled: false, enrolled: true, passkeys: 1, totp: false },
      { id: 'alex', username: 'alex', display_name: 'Alex', role: 'adult', created_at: this.iso(86400 * 10), last_seen_at: this.iso(3600), disabled: false, enrolled: true, passkeys: 0, totp: true },
    ]);
  }
  async users() {
    this.owner();
    return this.users_().map((u) => ({ ...u }));
  }
  async createUser(b: { display_name: string; role: W.PersonRole; username?: string }) {
    this.owner();
    if (!['owner', 'adult', 'guest'].includes(b.role)) throw new ApiError(422, 'conflict', 'role must be one of owner, adult, guest');
    const u: W.UserInfo = { id: this.id('usr'), username: b.username ?? null, display_name: b.display_name, role: b.role, created_at: this.iso(), last_seen_at: null, disabled: false, enrolled: false, passkeys: 0, totp: false };
    this.users_().push(u);
    return { ...u, one_time: { enrolment_code: MOCK_ENROL_CODE, enrolment_url: `http://box.local/signin#enrol=${MOCK_ENROL_CODE}`, expires_at: this.iso(-86400) } };
  }
  async updateUser(id: string, b: { display_name?: string; role?: W.PersonRole }) {
    this.owner();
    const u = this.users_().find((x) => x.id === id);
    if (!u) throw new ApiError(404, 'not_found', 'no such user');
    const owners = this.users_().filter((x) => x.role === 'owner' && !x.disabled);
    if (b.role && b.role !== 'owner' && u.role === 'owner' && owners.length === 1) throw new ApiError(409, 'conflict', 'the last owner cannot be demoted or disabled', 'last_owner');
    Object.assign(u, b);
    return { ...u };
  }
  async disableUser(id: string) {
    this.owner();
    const u = this.users_().find((x) => x.id === id);
    if (!u) throw new ApiError(404, 'not_found', 'no such user');
    const owners = this.users_().filter((x) => x.role === 'owner' && !x.disabled);
    if (u.role === 'owner' && owners.length === 1) throw new ApiError(409, 'conflict', 'the last owner cannot be demoted or disabled', 'last_owner');
    u.disabled = true;
    return { ...u };
  }
  private tokens_() {
    return (this.tokenRows ??= [
      { id: 'tok_ops', prefix: 'omk_agt_ab1', name: 'ops agent', principal_id: 'agent:ops', kind: 'agent', scopes: ['reader'], created_at: this.iso(86400 * 3), expires_at: this.iso(-86400 * 27), last_used_at: this.iso(120), revoked_at: null, source: 'api', owner_user_id: 'owner' },
    ]);
  }
  async tokens() {
    this.person();
    return this.tokens_().map((t) => ({ ...t }));
  }
  async createToken(b: { name: string; principal?: 'self' | { kind: 'agent'; id: string }; expires_in_days?: number }) {
    const p = this.person();
    const agent = typeof b.principal === 'object';
    const t: W.TokenInfo = { id: this.id('tok'), prefix: 'omk_demo_01', name: b.name, principal_id: agent ? (b.principal as { id: string }).id : p.id, kind: agent ? 'agent' : 'person', scopes: agent ? ['reader'] : ['*'], created_at: this.iso(), expires_at: this.iso(-86400 * (b.expires_in_days ?? 30)), last_used_at: null, revoked_at: null, source: 'api', owner_user_id: p.id };
    this.tokens_().push(t);
    return { ...t, one_time: { token: `omk_demo_${hex(t.id).slice(0, 24)}` } };
  }
  async rotateToken(id: string) {
    this.person();
    const t = this.tokens_().find((x) => x.id === id && !x.revoked_at);
    if (!t) throw new ApiError(404, 'not_found', 'no such token');
    return { ...t, one_time: { token: `omk_demo_${hex(id + 'rot').slice(0, 24)}` } };
  }
  async revokeToken(id: string) {
    this.person();
    const t = this.tokens_().find((x) => x.id === id);
    if (!t) throw new ApiError(404, 'not_found', 'no such token');
    t.revoked_at = this.iso();
  }

  // ---- notifications ----------------------------------------------------------------------------
  private notes_() {
    return (this.notes ??= [
      { id: 'ntf_1', severity: 'warning', topic: 'backups', title: 'Backup is two days behind', body: 'The USB destination was not found.', link: null, source: 'system', action_id: null, alert_id: 'alr_1', created_at: this.iso(3600), read_at: null },
      { id: 'ntf_2', severity: 'info', topic: 'approvals', title: 'A request is waiting for you', body: 'ops-agent asked to install an app.', link: '/approvals', source: 'system', action_id: 'act-0001', alert_id: null, created_at: this.iso(7200), read_at: null },
      { id: 'ntf_3', severity: 'info', topic: 'updates', title: 'Update installed', body: 'The hub updated and the health check passed.', link: null, source: 'system', action_id: null, alert_id: null, created_at: this.iso(86400), read_at: this.iso(80000) },
    ]);
  }
  async notifications(o: { unread?: boolean } = {}) {
    this.person();
    return this.notes_().filter((n) => !o.unread || !n.read_at).map((n) => ({ ...n }));
  }
  async markRead(id: string) {
    this.person();
    const n = this.notes_().find((x) => x.id === id);
    if (!n) throw new ApiError(404, 'not_found', 'no such notification');
    n.read_at ??= this.iso();
    return { ...n };
  }
  async markAllRead() {
    this.person();
    const open = this.notes_().filter((n) => !n.read_at);
    open.forEach((n) => (n.read_at = this.iso()));
    return { marked: open.length };
  }
  async channels() {
    this.person();
    return this.channelRows.map((c) => ({ ...c }));
  }
  async createChannel(b: W.ChannelInput) {
    const p = this.person();
    if (!['unifiedpush', 'webhook', 'email', 'ntfy'].includes(b.kind)) throw new ApiError(422, 'conflict', 'kind must be one of unifiedpush, webhook, email (or ntfy)');
    const c: W.ChannelInfo = { id: this.id('chn'), kind: b.kind, label: b.label, content_level: b.content_level ?? 'title', config: b.config, verified: false, state: 'active', last_error: null, owner_person_id: p.id, secret: b.secret ? 'provided' : null, created_at: this.iso(), updated_at: this.iso() };
    this.channelRows = [...this.channelRows, c];
    return { ...c };
  }
  async deleteChannel(id: string) {
    this.person();
    if (!this.channelRows.some((c) => c.id === id)) throw new ApiError(404, 'not_found', 'no such channel');
    this.channelRows = this.channelRows.filter((c) => c.id !== id);
  }
  async testChannel(id: string) {
    this.person();
    const c = this.channelRows.find((x) => x.id === id);
    if (!c) throw new ApiError(404, 'not_found', 'no such channel');
    c.verified = true;
    return { ok: true };
  }

  // ---- monitoring --------------------------------------------------------------------------------
  private alerts_() {
    return (this.alertRows ??= [
      { schema: 'onemind.alert/v1', id: 'alr_1', type: 'app.unhealthy', severity: 'warning', title: 'Vaultwarden is not answering its health check', body: 'The check has failed for 3 minutes.', subject: { app_id: 'vaultwarden' }, state: 'open', occurrences: 3, flapping: false, opened_at: this.iso(900), updated_at: this.iso(60), resolved_at: null, fix: { type: 'app.install', params: { app_id: 'vaultwarden' }, label: 'Reinstall Vaultwarden' }, learn_more_url: null, topic: 'apps', link: null, acked_by: null, acked_at: null },
      { schema: 'onemind.alert/v1', id: 'alr_2', type: 'disk.low', severity: 'critical', title: 'Less than 10% free on /data', body: 'Free some space or add a disk.', subject: { node_id: '3f9c2a1b7d4e' }, state: 'open', occurrences: 1, flapping: false, opened_at: this.iso(7200), updated_at: this.iso(7200), resolved_at: null, fix: null, learn_more_url: null, topic: 'storage', link: null, acked_by: null, acked_at: null },
    ]);
  }
  async monitoring(): Promise<W.MonitoringSummary> {
    this.auth();
    const open = this.alerts_().filter((a) => a.state !== 'resolved');
    const count = (s: W.Severity) => open.filter((a) => a.severity === s).length;
    return { nodes: { online: 2, stale: 1, offline: 1 }, apps: { healthy: 5, unhealthy: 1, starting: 0, stopped: 0, unknown: 0 }, open_alerts: { info: count('info'), warning: count('warning'), critical: count('critical') }, storage: [{ node_id: '3f9c2a1b7d4e', state: 'protected' }], at: this.iso() };
  }
  async alerts(state = 'open') {
    this.auth();
    const want = state === 'open' ? ['open', 'acknowledged'] : state.split(',');
    return this.alerts_().filter((a) => want.includes(a.state)).map((a) => ({ ...a }));
  }
  private alert(id: string) {
    const a = this.alerts_().find((x) => x.id === id);
    if (!a) throw new ApiError(404, 'not_found', 'no such alert');
    return a;
  }
  async ackAlert(id: string) {
    const p = this.auth();
    if (!(p.kind === 'person' && (p.role === 'owner' || p.role === 'adult'))) throw new ApiError(403, 'permission_denied', 'only owners and adults acknowledge alerts');
    const a = this.alert(id);
    if (a.state !== 'open') throw new ApiError(409, 'conflict', `alert is ${a.state}`);
    a.state = 'acknowledged';
    a.acked_by = p.id;
    a.acked_at = this.iso();
    return { ...a };
  }
  async resolveAlert(id: string) {
    this.owner();
    const a = this.alert(id);
    if (a.state === 'resolved') throw new ApiError(409, 'conflict', 'alert is already resolved');
    a.state = 'resolved';
    a.resolved_at = this.iso();
    return { ...a };
  }
  async askToFix(id: string) {
    const p = this.auth();
    if (p.role !== 'owner' && p.kind !== 'agent') throw new ApiError(403, 'permission_denied', 'only owners and agents request fixes');
    const a = this.alert(id);
    if (!a.fix) throw new ApiError(409, 'conflict', 'this alert has no fix');
    return this.fileAction(a.fix.type, a.fix.params);
  }

  // ---- audit -------------------------------------------------------------------------------------
  private chain(): W.AuditRecord[] {
    const rows: Array<[string, W.AuditRecord['principal'], Record<string, unknown>, string | null]> = [
      ['auth.login.succeeded', { id: 'owner', kind: 'person', role: 'owner' }, { method: 'password' }, null],
      ['action.requested', { id: 'ops-agent', kind: 'agent' }, { type: 'app.install', app_id: 'vaultwarden' }, 'act-0001'],
      ['action.approved', { id: 'owner', kind: 'person', role: 'owner' }, { type: 'app.install' }, 'act-0001'],
      ['notify.alert.opened', null, { alert_id: 'alr_1' }, null],
    ];
    let prev = '0'.repeat(64);
    return rows.map(([event, principal, data, action_id], i) => {
      const hash = hex(prev + event + i);
      const r: W.AuditRecord = { seq: i + 1, ts: this.iso((rows.length - i) * 600), event, principal, action_id, data, hash, prev_hash: prev };
      prev = hash;
      return r;
    });
  }
  async auditEvents(o: { limit?: number; after_seq?: number } = {}) {
    this.owner();
    return this.chain().filter((r) => r.seq > (o.after_seq ?? 0)).slice(0, o.limit ?? 200);
  }
  async auditVerify(): Promise<W.AuditVerifyResult> {
    this.owner();
    const c = this.chain();
    const head = c[c.length - 1]!;
    return { ok: true, records: c.length, first_bad_seq: null, head: { seq: head.seq, hash: head.hash }, checked_at: this.iso(), reason: 'ok' };
  }
}

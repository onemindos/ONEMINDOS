// SPDX-License-Identifier: Apache-2.0
import type { WiringApi } from './wiring';
import { getPasskey } from '../lib/webauthn';
import type * as W from './wiring';
import { OneMind, OneMindError, type operations, type components } from '@onemind/sdk';
import {
  ApiError,
  type Action,
  type ActionRequest,
  type ActionType, type AppParams, type PlanPreview, type AppSettings,
  type AppDependencies, type AppHostPorts, type CommunitySource, type ComposeResult,
  type ApiErrorBody,
  type CatalogApp,
  type Instance,
  type MachineCapabilities,
  type MachineRecord,
  type NodeRecord,
} from './types';

/**
 * Everything the dashboard is allowed to ask the hub. One method per §3 route,
 * nothing else (contract §5: "it calls only the §3 API").
 */
export type PluginKeyInfo = components["schemas"]["SigningKey"];
export type PluginKeyInput = components["schemas"]["KeyRequest"];
export type PluginKeyRevokeInput = components["schemas"]["RevokeRequest"];

export interface OneMindApi extends WiringApi {
  pluginSigningKeys?(): Promise<components["schemas"]["SigningKeys"]>;
  requestPluginSigningKey?(body: PluginKeyInput): Promise<components["schemas"]["Action"]>;
  revokePluginSigningKey?(keyId: string, body: PluginKeyRevokeInput): Promise<components["schemas"]["Action"]>;
  onboardingSettings(): Promise<FirstRunSettings>;
  saveOnboardingSettings(body: FirstRunSettingsBody): Promise<FirstRunSettings>;
  backupDestinations(): Promise<BackupDestinationRecord[]>;
  healthz(): Promise<{ ok: boolean }>;
  instance(): Promise<Instance>;
  nodes(): Promise<NodeRecord[]>;
  node(nodeId: string): Promise<NodeRecord>;
  apps(): Promise<CatalogApp[]>;
  /** MACH-01: absent on the mock gateway, which has no machines. */
  machines?(): Promise<MachineRecord[]>;
  machineCapabilities?(): Promise<MachineCapabilities>;
  appPlan?(id: string): Promise<PlanPreview>;
  previewAction?(type: ActionType, params: AppParams): Promise<PlanPreview>;
  appSettings?(id: string): Promise<AppSettings>;
  appLogs?(id: string): Promise<string>;
  appDependencies?(id: string): Promise<AppDependencies>;
  appHostPorts?(id: string): Promise<AppHostPorts>;
  sources?(): Promise<CommunitySource[]>;
  /** Files a `source.add` request; it waits in Approvals until the owner approves it. */
  requestSourceAdd?(params: SourceAddParams, key: { idempotency_key: string; expires_at: string }): Promise<Action>;
  convertCompose?(body: { app_id: string; name?: string; compose: string }): Promise<ComposeResult>;
  createAction(req: ActionRequest): Promise<Action>;
  actions(): Promise<Action[]>;
  action(id: string): Promise<Action>;
  approve(id: string): Promise<Action>;
  deny(id: string): Promise<Action>;
  /** Hub clock minus browser clock (ms), learned from responses; undefined until known. */
  hubOffsetMs(): number | undefined;
}

export interface FirstRunSettingsBody {
  box_name: string;
  time_zone: string;
  backup_choice: 'usb' | 'peer' | 's3' | 'later';
  backup_destination_id: string | null;
}
export interface FirstRunSettings extends Omit<FirstRunSettingsBody, 'box_name' | 'time_zone'> {
  box_name: string | null;
  time_zone: string | null;
  saved: boolean;
}
export interface SourceAddParams { name: string; url: string; commit: string }
export interface BackupDestinationRecord { id: string; kind: string; label: string }

const KNOWN_CODES = new Set([
  'permission_denied',
  'stale_precondition',
  'expired',
  'conflict',
  'outcome_unknown',
  'not_found',
  'unauthenticated',
  'rate_limited',
  'payload_too_large',
  'policy_refused',
]);

function isErrorBody(v: unknown): v is ApiErrorBody {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as ApiErrorBody).error === 'string' &&
    KNOWN_CODES.has((v as ApiErrorBody).error)
  );
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** Real client: talks to the gateway over HTTP with a bearer token. */
export class HttpApi implements OneMindApi {
  private readonly sdk: OneMind;
  onboardingSettings = () => this.req<FirstRunSettings>('GET', '/v1/onboarding/settings');
  saveOnboardingSettings = (body: FirstRunSettingsBody) => this.req<FirstRunSettings>('PUT', '/v1/onboarding/settings', body);
  backupDestinations = () => this.req<BackupDestinationRecord[]>('GET', '/v1/backups/destinations', undefined, 'array');
  private readonly base: string;
  private readonly token: string;
  private readonly fetchFn: FetchLike;
  private offsetMs: number | undefined;

  constructor(opts: { token: string; baseUrl?: string; fetchFn?: FetchLike }) {
    this.base = (opts.baseUrl ?? '').replace(/\/$/, '');
    this.token = opts.token;
    this.fetchFn = opts.fetchFn ?? ((input, init) => fetch(input, init));
    this.sdk = new OneMind({ baseUrl: new URL(this.base || '/', globalThis.location?.origin ?? 'http://localhost').href, token: opts.token, fetch: (input, init) => this.fetchFn(String(input), init), retries: 1 });
  }

  /**
   * `shape` is what a 2xx body must be. Anything else (an HTML page from a proxy
   * or SPA fallback, an empty body, the wrong JSON type) is an error, not data.
   */
  private async req<T>(method: string, path: string, body?: unknown, shape: 'object' | 'array' | 'text' = 'object', bearer?: string): Promise<T> {
    let res: Response;
    try {
      // The SDK's JSON-only call cannot decode text/plain logs; reuse its authenticated
      // transport directly for that one route rather than invent another token provider.
      const fetchFn = shape === 'text' ? this.sdk.fetchImpl : this.fetchFn;
      res = await fetchFn(shape === 'text' ? this.sdk.baseUrl + path : this.base + path, {
        method,
        headers: {
          Accept: shape === 'text' ? 'text/plain' : 'application/json',
          ...((bearer ?? this.token) ? { Authorization: `Bearer ${bearer ?? this.token}` } : {}),
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(shape === 'text' ? await this.sdk.authHeader() : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'Network error');
    }
    // The hub stamps last_seen with its own clock; the Date header lets the UI
    // age it on that clock instead of the browser's (1 s resolution is enough
    // for the 30 s / 120 s thresholds).
    const hubDate = Date.parse(res.headers.get('Date') ?? '');
    if (!Number.isNaN(hubDate)) this.offsetMs = hubDate - Date.now();
    const text = await res.text();
    let data: unknown = undefined;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = undefined;
      }
    }
    if (!res.ok) {
      if (isErrorBody(data)) throw new ApiError(res.status, data.error, data.message, data.reason);
      const code = res.status === 401 ? 'unauthenticated' : res.status === 404 ? 'not_found' : 'unknown';
      throw new ApiError(res.status, code, `HTTP ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    if (shape === 'text') {
      if (!res.headers.get('Content-Type')?.startsWith('text/plain')) throw new ApiError(res.status, 'unknown', 'Unexpected response from the hub');
      return text as T;
    }
    const valid =
      shape === 'array' ? Array.isArray(data) : typeof data === 'object' && data !== null && !Array.isArray(data);
    if (!valid) throw new ApiError(res.status, 'unknown', 'Unexpected response from the hub');
    return data as T;
  }

  hubOffsetMs() {
    return this.offsetMs;
  }
  healthz() {
    return this.req<{ ok: boolean }>('GET', '/healthz');
  }
  instance() {
    return this.req<Instance>('GET', '/v1/instance');
  }
  nodes() {
    return this.req<NodeRecord[]>('GET', '/v1/nodes', undefined, 'array');
  }
  node(nodeId: string) {
    return this.req<NodeRecord>('GET', `/v1/nodes/${encodeURIComponent(nodeId)}`);
  }
  apps() {
    return this.req<CatalogApp[]>('GET', '/v1/apps', undefined, 'array');
  }
  /**
   * POST /v1/actions with the outcome rules every request shares: a lost reply (network, 408,
   * 5xx or an unreadable 2xx) is outcome_unknown, so the caller keeps the idempotency key and a
   * retry cannot file a second action; any other 4xx is a clear refusal. A reply only counts when
   * it is the action that was asked for (type, key, state, expiry, plus the caller's own checks).
   */
  private async fileAction(body: { type: string; params: unknown; idempotency_key: string; expires_at: string }, matches: (a: Action) => boolean): Promise<Action> {
    const ambiguous = () => new ApiError(0, 'outcome_unknown', 'The request may have been recorded, but the gateway did not return a complete matching action. Retry to confirm it.');
    let action: Action;
    try { action = await this.sdkCall<Action>('POST', '/v1/actions', body); }
    catch (e) {
      if (!(e instanceof ApiError) || e.status === 0 || e.status === 408 || e.status >= 500 || (e.status >= 200 && e.status < 300)) throw ambiguous();
      throw e;
    }
    const states = new Set(['requested', 'awaiting_approval', 'accepted', 'dispatched', 'succeeded', 'failed', 'outcome_unknown', 'expired', 'cancelled']);
    if (typeof action.id !== 'string' || !action.id || (action.type as string) !== body.type || !states.has(action.state) || !action.params || typeof action.params !== 'object' || action.idempotency_key !== body.idempotency_key || !Number.isFinite(Date.parse(action.expires_at))) throw ambiguous();
    if (action.progress && (typeof action.progress.step !== 'string' || !Number.isFinite(action.progress.pct) || action.progress.pct < 0 || action.progress.pct > 100)) throw ambiguous();
    if (!matches(action)) throw ambiguous();
    return action;
  }
  createAction(req: ActionRequest) {
    return this.fileAction(req, (action) => {
      if (action.params.app_id !== req.params.app_id) return false;
      if (req.params.app_id === undefined && action.params.name !== req.params.name) return false;
      if (req.params.settings && (!action.params.settings || Object.keys(action.params.settings).length !== Object.keys(req.params.settings).length || Object.entries(req.params.settings).some(([k, v]) => action.params.settings?.[k] !== v))) return false;
      return !req.plan_sha256 || action.plan_sha256 === req.plan_sha256;
    });
  }
  private async sdkCall<T>(method: 'GET' | 'POST', path: string, body?: unknown, array = false, retry?: boolean): Promise<T> {
    try {
      const value = await this.sdk.call<T>({ method, path, body, retry });
      if (!value || typeof value !== 'object' || Array.isArray(value) !== array) throw new ApiError(200, 'unknown', 'Unexpected response from the hub');
      return value;
    }
    catch (e) {
      if (e instanceof OneMindError) throw new ApiError(e.status, KNOWN_CODES.has(e.code) || e.code === 'network' ? e.code as ApiError['code'] : 'unknown', e.message, e.reason);
      throw e;
    }
  }
  pluginSigningKeys() { return this.sdkCall<components["schemas"]["SigningKeys"]>('GET', '/v1/plugin-trust/keys'); }
  requestPluginSigningKey(body: PluginKeyInput) { return this.sdkCall<components["schemas"]["Action"]>('POST', '/v1/plugin-trust/keys/requests', body); }
  revokePluginSigningKey(keyId: string, body: PluginKeyRevokeInput) { return this.sdkCall<components["schemas"]["Action"]>('POST', `/v1/plugin-trust/keys/${encodeURIComponent(keyId)}/revoke`, body); }
  machines() { return this.req<MachineRecord[]>('GET', '/v1/machines', undefined, 'array'); }
  machineCapabilities() { return this.req<MachineCapabilities>('GET', '/v1/machines/capabilities'); }
  appPlan(id: string) { return this.sdkCall<PlanPreview>('GET', `/v1/apps/${encodeURIComponent(id)}/plan`); }
  previewAction(type: ActionType, params: AppParams) { return this.sdkCall<PlanPreview>('POST', '/v1/plans', { type, params }); }
  async appSettings(id: string) {
    const raw = await this.sdkCall<operations['apps.settings']['responses'][200]['content']['application/json']>('GET', `/v1/apps/${encodeURIComponent(id)}/settings`);
    if (!raw || typeof raw !== 'object' || !('fields' in raw) || !Array.isArray(raw.fields) || !('values' in raw)) throw new ApiError(200, 'unknown', 'Invalid gateway settings');
    for (const f of raw.fields) {
      if (!f || typeof f !== 'object' || typeof f.name !== 'string' || !['string', 'integer', 'number', 'boolean'].includes(f.type) || (f.enum !== undefined && (!Array.isArray(f.enum) || f.enum.some((v: unknown) => !['string', 'number', 'boolean'].includes(typeof v))))) throw new ApiError(200, 'unknown', 'Invalid gateway settings field');
    }
    if (raw.values !== null && (typeof raw.values !== 'object' || Array.isArray(raw.values) || Object.values(raw.values).some((v) => !['string', 'number', 'boolean'].includes(typeof v)))) throw new ApiError(200, 'unknown', 'Invalid gateway setting values');
    return raw as AppSettings;
  }
  // ---- §12.22 app store depth (#57). The SDK types these bodies as unknown, so each is checked here.
  async appDependencies(id: string) {
    const raw = await this.sdkCall<AppDependencies>('GET', `/v1/apps/${encodeURIComponent(id)}/dependencies`);
    const okChoice = (c: AppDependencies['requires'][number]['choices'][number]) => !!c && typeof c.id === 'string' && typeof c.installed === 'boolean' && typeof c.in_catalog === 'boolean';
    if (!Array.isArray(raw.requires) || !Array.isArray(raw.dependents) || raw.requires.some((r) => !r || typeof r.id !== 'string' || !Array.isArray(r.choices) || !r.choices.every(okChoice)) || raw.dependents.some((d) => !d || typeof d.id !== 'string')) throw new ApiError(200, 'unknown', 'Invalid gateway dependencies');
    return raw;
  }
  async appHostPorts(id: string) {
    const raw = await this.sdkCall<AppHostPorts>('GET', `/v1/apps/${encodeURIComponent(id)}/host-ports`);
    const port = (p: { port: number; protocol: string }) => !!p && Number.isInteger(p.port) && typeof p.protocol === 'string';
    if (!Array.isArray(raw.declared) || !Array.isArray(raw.conflicts) || !raw.declared.every(port) || !raw.conflicts.every((c) => port(c) && typeof c.with === 'string')) throw new ApiError(200, 'unknown', 'Invalid gateway host ports');
    return raw;
  }
  async sources() {
    const raw = await this.sdkCall<CommunitySource[]>('GET', '/v1/sources', undefined, true);
    if (raw.some((s) => !s || typeof s.id !== 'string' || typeof s.name !== 'string' || typeof s.commit !== 'string' || !Array.isArray(s.apps) || !Array.isArray(s.errors))) throw new ApiError(200, 'unknown', 'Invalid gateway sources');
    return raw;
  }
  requestSourceAdd(params: SourceAddParams, key: { idempotency_key: string; expires_at: string }) {
    return this.fileAction({ type: 'source.add', params, ...key }, (action) => {
      const got = action.params as unknown as Record<string, unknown>;
      return Object.keys(got).length === 3 && got.name === params.name && got.url === params.url && got.commit === params.commit
        && Date.parse(action.expires_at) === Date.parse(key.expires_at);
    });
  }
  async convertCompose(body: { app_id: string; name?: string; compose: string }) {
    const raw = await this.sdkCall<ComposeResult>('POST', '/v1/deploy/compose', body);
    if (typeof raw.ok !== 'boolean' || !raw.files || typeof raw.files !== 'object' || !Array.isArray(raw.refusals) || !Array.isArray(raw.warnings) || Object.values(raw.files).some((v) => typeof v !== 'string')) throw new ApiError(200, 'unknown', 'Invalid gateway Compose result');
    return raw;
  }
  appLogs(id: string) { return this.req<string>('GET', `/v1/apps/${encodeURIComponent(id)}/logs?tail=200`, undefined, 'text'); }
  actions() {
    return this.req<Action[]>('GET', '/v1/actions', undefined, 'array');
  }
  action(id: string) {
    return this.req<Action>('GET', `/v1/actions/${encodeURIComponent(id)}`);
  }
  async approve(id: string) {
    const path = `/v1/actions/${encodeURIComponent(id)}/approve`;
    try { return await this.req<Action>('POST', path); }
    catch (error) {
      if (!(error instanceof ApiError) || error.reason !== 'step_up_required') throw error;
      const options = await this.sdkCall<components['schemas']['ApprovalChallenge']>('POST', path + '-options', {}, false, false);
      const assertion = await getPasskey(options.publicKey);
      return this.sdkCall<Action>('POST', path, {
        webauthn: assertion, ...(options.plan_sha256 ? { plan_sha256: options.plan_sha256 } : {}),
      }, false, false); // a consumed authenticator assertion must never be retried automatically
    }
  }
  deny(id: string) {
    return this.req<Action>('POST', `/v1/actions/${encodeURIComponent(id)}/deny`);
  }

  // ---- §12 routes (see wiring.ts). One method per route. -------------------------------------------
  loginOptions() {
    return this.req<W.WebAuthnOptions>('POST', '/v1/auth/login/options', {});
  }
  loginPassword(b: { username: string; password: string; totp?: string }) {
    return this.req<W.LoginResult>('POST', '/v1/auth/login', { ...b, client: 'app', client_name: 'dashboard' });
  }
  loginPasskey(credential: Record<string, unknown>) {
    return this.req<W.LoginResult>('POST', '/v1/auth/login', { passkey: credential, client: 'app', client_name: 'dashboard' });
  }
  setup(setupToken: string, b: { username: string; display_name: string; password: string }) {
    return this.req<W.LoginResult>('POST', '/v1/auth/setup', { ...b, client: 'app' }, 'object', setupToken);
  }
  enrol(b: { code: string; username?: string; password: string }) {
    return this.req<W.LoginResult>('POST', '/v1/auth/enrol', { ...b, client: 'app' });
  }
  me() {
    return this.req<W.Me>('GET', '/v1/me');
  }
  async logout() {
    await this.req<void>('POST', '/v1/auth/logout', {});
  }
  sessions() {
    return this.req<W.SessionInfo[]>('GET', '/v1/auth/sessions', undefined, 'array');
  }
  async revokeSession(id: string) {
    await this.req<void>('DELETE', `/v1/auth/sessions/${encodeURIComponent(id)}`);
  }
  passkeys() {
    return this.req<W.PasskeyInfo[]>('GET', '/v1/auth/passkeys', undefined, 'array');
  }
  passkeyRegisterOptions() {
    return this.req<W.WebAuthnOptions>('POST', '/v1/auth/passkeys/register/options', {});
  }
  passkeyRegister(credential: Record<string, unknown>, label?: string) {
    return this.req<W.PasskeyInfo>('POST', '/v1/auth/passkeys/register', { credential, label });
  }
  async deletePasskey(id: string) {
    await this.req<void>('DELETE', `/v1/auth/passkeys/${encodeURIComponent(id)}`);
  }
  users() {
    return this.req<W.UserInfo[]>('GET', '/v1/users', undefined, 'array');
  }
  createUser(b: { display_name: string; role: W.PersonRole; username?: string }) {
    return this.req<W.UserCreated>('POST', '/v1/users', b);
  }
  updateUser(id: string, b: { display_name?: string; role?: W.PersonRole }) {
    return this.req<W.UserInfo>('PATCH', `/v1/users/${encodeURIComponent(id)}`, b);
  }
  disableUser(id: string) {
    return this.req<W.UserInfo>('POST', `/v1/users/${encodeURIComponent(id)}/disable`, {});
  }
  familyProfile(id: string) {
    return this.req<W.FamilyProfile>('GET', `/v1/family/profiles/${encodeURIComponent(id)}`);
  }
  tokens() {
    return this.req<W.TokenInfo[]>('GET', '/v1/tokens', undefined, 'array');
  }
  createToken(b: { name: string; principal?: 'self' | { kind: 'agent'; id: string }; expires_in_days?: number }) {
    return this.req<W.TokenCreated>('POST', '/v1/tokens', b);
  }
  rotateToken(id: string, graceS = 0) {
    return this.req<W.TokenCreated>('POST', `/v1/tokens/${encodeURIComponent(id)}/rotate`, { grace_s: graceS });
  }
  async revokeToken(id: string) {
    await this.req<void>('DELETE', `/v1/tokens/${encodeURIComponent(id)}`);
  }
  notifications(o: { unread?: boolean; limit?: number } = {}) {
    const q = new URLSearchParams();
    if (o.unread) q.set('unread', 'true');
    q.set('limit', String(o.limit ?? 100));
    return this.req<W.NotificationItem[]>('GET', `/v1/notifications?${q}`, undefined, 'array');
  }
  markRead(id: string) {
    return this.req<W.NotificationItem>('POST', `/v1/notifications/${encodeURIComponent(id)}/read`, {});
  }
  markAllRead() {
    return this.req<{ marked: number }>('POST', '/v1/notifications/read-all', {});
  }
  channels() {
    return this.req<W.ChannelInfo[]>('GET', '/v1/notifications/channels', undefined, 'array');
  }
  createChannel(b: W.ChannelInput) {
    return this.req<W.ChannelInfo>('POST', '/v1/notifications/channels', b);
  }
  async deleteChannel(id: string) {
    await this.req<void>('DELETE', `/v1/notifications/channels/${encodeURIComponent(id)}`);
  }
  testChannel(id: string) {
    return this.req<{ ok?: boolean; error?: string | null }>('POST', `/v1/notifications/channels/${encodeURIComponent(id)}/test`, {});
  }
  monitoring() {
    return this.req<W.MonitoringSummary>('GET', '/v1/monitoring/summary');
  }
  alerts(state = 'open') {
    return this.req<W.AlertInfo[]>('GET', `/v1/alerts?state=${encodeURIComponent(state)}`, undefined, 'array');
  }
  ackAlert(id: string) {
    return this.req<W.AlertInfo>('POST', `/v1/alerts/${encodeURIComponent(id)}/ack`, {});
  }
  resolveAlert(id: string) {
    return this.req<W.AlertInfo>('POST', `/v1/alerts/${encodeURIComponent(id)}/resolve`, {});
  }
  askToFix(id: string, reason?: string) {
    // approve is always false: the request waits in Approvals for a human.
    return this.req<Action>('POST', `/v1/alerts/${encodeURIComponent(id)}/fix`, { approve: false, reason: reason ?? null });
  }
  auditEvents(o: { limit?: number; after_seq?: number } = {}) {
    const q = new URLSearchParams({ limit: String(o.limit ?? 200) });
    if (o.after_seq) q.set('after_seq', String(o.after_seq));
    return this.req<W.AuditRecord[]>('GET', `/v1/audit/events?${q}`, undefined, 'array');
  }
  auditVerify() {
    return this.req<W.AuditVerifyResult>('GET', '/v1/audit/verify');
  }
}

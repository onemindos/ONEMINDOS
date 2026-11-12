// SPDX-License-Identifier: Apache-2.0
import type { WiringApi } from './wiring';
import type * as W from './wiring';
import {
  ApiError,
  type Action,
  type ActionRequest,
  type ApiErrorBody,
  type CatalogApp,
  type Instance,
  type NodeRecord,
} from './types';

/**
 * Everything the dashboard is allowed to ask the hub. One method per §3 route,
 * nothing else (contract §5: "it calls only the §3 API").
 */
export interface OneMindApi extends WiringApi {
  healthz(): Promise<{ ok: boolean }>;
  instance(): Promise<Instance>;
  nodes(): Promise<NodeRecord[]>;
  node(nodeId: string): Promise<NodeRecord>;
  apps(): Promise<CatalogApp[]>;
  createAction(req: ActionRequest): Promise<Action>;
  actions(): Promise<Action[]>;
  action(id: string): Promise<Action>;
  approve(id: string): Promise<Action>;
  deny(id: string): Promise<Action>;
  /** Hub clock minus browser clock (ms), learned from responses; undefined until known. */
  hubOffsetMs(): number | undefined;
}

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
  private readonly base: string;
  private readonly token: string;
  private readonly fetchFn: FetchLike;
  private offsetMs: number | undefined;

  constructor(opts: { token: string; baseUrl?: string; fetchFn?: FetchLike }) {
    this.base = (opts.baseUrl ?? '').replace(/\/$/, '');
    this.token = opts.token;
    this.fetchFn = opts.fetchFn ?? ((input, init) => fetch(input, init));
  }

  /**
   * `shape` is what a 2xx body must be. Anything else (an HTML page from a proxy
   * or SPA fallback, an empty body, the wrong JSON type) is an error, not data.
   */
  private async req<T>(method: string, path: string, body?: unknown, shape: 'object' | 'array' = 'object', bearer?: string): Promise<T> {
    let res: Response;
    try {
      res = await this.fetchFn(this.base + path, {
        method,
        headers: {
          Accept: 'application/json',
          ...((bearer ?? this.token) ? { Authorization: `Bearer ${bearer ?? this.token}` } : {}),
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
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
  createAction(req: ActionRequest) {
    return this.req<Action>('POST', '/v1/actions', req);
  }
  actions() {
    return this.req<Action[]>('GET', '/v1/actions', undefined, 'array');
  }
  action(id: string) {
    return this.req<Action>('GET', `/v1/actions/${encodeURIComponent(id)}`);
  }
  approve(id: string) {
    return this.req<Action>('POST', `/v1/actions/${encodeURIComponent(id)}/approve`);
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

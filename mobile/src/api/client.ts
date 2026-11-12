// SPDX-License-Identifier: Apache-2.0
// Started as a copy of dashboard/src/api/client.ts (feat/gwmcp, commit 951470f). The §3 methods keep the
// dashboard's behaviour; the §12 methods (identity, notifications, push, devices, events) are mobile
// additions until the generated `@onemind/sdk` replaces both copies (DEV-SDK-4).
import {
  ApiError,
  type Action,
  type ActionRequest,
  type AlertRecord,
  type ApiErrorBody,
  type ApproveBody,
  type ApproveOptions,
  type CatalogApp,
  type DeviceRequest,
  type DeviceRequestBody,
  type InboxItem,
  type Instance,
  type LoginResult,
  type Me,
  type NodeRecord,
  type Plan,
  type PushRegistration,
  type PushRegistrationRequest,
  type WebAuthnAssertion,
  type WebAuthnAttestation,
  type WebAuthnCreationOptions,
  type WebAuthnRequestOptions,
} from './types';

/**
 * Operations the phone feature-detects (§12: "a route exists only once its module ships; until then it is
 * absent from /openapi.json"). Keys are `METHOD path` with every path parameter written `{}`.
 */
export const OP = {
  me: 'GET /v1/me',
  events: 'GET /v1/events',
  approveOptions: 'POST /v1/actions/{}/approve-options',
  preview: 'GET /v1/actions/{}/preview',
  notifications: 'GET /v1/notifications',
  alerts: 'GET /v1/alerts',
  pushRegister: 'POST /v1/push/registrations',
  vapidKey: 'GET /v1/push/vapid-public-key',
  loginOptions: 'POST /v1/auth/login/options',
  passkeyRegisterOptions: 'POST /v1/auth/passkeys/register/options',
  /** Not in §12.6 (it returns a refresh_token but names no route); used only when the gateway lists it. */
  authRefresh: 'POST /v1/auth/refresh',
  deviceRequest: 'POST /v1/devices/requests',
  deviceToken: 'POST /v1/devices/token',
} as const;

export type Op = (typeof OP)[keyof typeof OP];

/** What this gateway serves, read once from `/openapi.json`. */
export class Features {
  private readonly ops: ReadonlySet<string>;
  constructor(ops: Iterable<string>, readonly source: 'openapi' | 'demo' | 'unknown') {
    this.ops = new Set(ops);
  }
  has(op: Op | string): boolean {
    return this.ops.has(op);
  }
  /** A v0 gateway (or one whose /openapi.json could not be read): only §3 routes are used. */
  static none(): Features {
    return new Features([], 'unknown');
  }
  static fromOpenApi(spec: unknown): Features {
    const paths = (spec as { paths?: Record<string, Record<string, unknown>> } | null)?.paths;
    const ops: string[] = [];
    if (paths && typeof paths === 'object') {
      for (const [path, item] of Object.entries(paths)) {
        const norm = path.replace(/\{[^}]*\}/g, '{}');
        for (const method of Object.keys(item ?? {})) ops.push(`${method.toUpperCase()} ${norm}`);
      }
    }
    return new Features(ops, 'openapi');
  }
}

/** Credentials for each request. A session token can be renewed once after a 401. */
export interface TokenSource {
  current(): string | undefined;
  /** Returns a fresh bearer, or undefined when the session cannot be renewed (sign in again). */
  refresh?(): Promise<string | undefined>;
}

/** WebAuthn options as the gateway sends them: bare JSON, or wrapped in `publicKey` (both are common). */
export type LoginOptions = Partial<WebAuthnRequestOptions> & { publicKey?: Partial<WebAuthnRequestOptions> };
export type RegisterOptions = Partial<WebAuthnCreationOptions> & { publicKey?: Partial<WebAuthnCreationOptions> };

/**
 * Everything the phone may ask the hub: the §3 routes plus the §12 routes it uses.
 * The phone never decides anything; every write is a request or a decision the gateway checks.
 */
export interface OneMindApi {
  healthz(): Promise<{ ok: boolean }>;
  instance(): Promise<Instance>;
  nodes(): Promise<NodeRecord[]>;
  node(nodeId: string): Promise<NodeRecord>;
  apps(): Promise<CatalogApp[]>;
  createAction(req: ActionRequest): Promise<Action>;
  actions(): Promise<Action[]>;
  action(id: string): Promise<Action>;
  /** §3 approve; §12.4 adds the optional `{plan_sha256, webauthn}` body. */
  approve(id: string, body?: ApproveBody): Promise<Action>;
  /** §3 deny; §12.4 adds an optional reason shown to the requester. */
  deny(id: string, reason?: string): Promise<Action>;
  /** Hub clock minus phone clock (ms), learned from responses; undefined until known. */
  hubOffsetMs(): number | undefined;

  // §12 (feature-detected with `features()`).
  features(): Promise<Features>;
  me(): Promise<Me>;
  approveOptions(id: string): Promise<ApproveOptions>;
  preview(id: string): Promise<{ plan: Plan; plan_sha256: string }>;
  notifications(q?: { unread?: boolean; limit?: number }): Promise<InboxItem[]>;
  notification(id: string): Promise<InboxItem>;
  markRead(id: string): Promise<void>;
  markAllRead(): Promise<{ marked: number }>;
  alerts(state?: 'open'): Promise<AlertRecord[]>;
  ackAlert(id: string): Promise<AlertRecord>;
  /** Files the alert's fix as a normal request (202); the owner still approves it. */
  fixAlert(id: string): Promise<Action>;
  pushRegister(req: PushRegistrationRequest): Promise<PushRegistration>;
  pushRegistrations(): Promise<PushRegistration[]>;
  pushUnregister(id: string): Promise<void>;
  vapidPublicKey(): Promise<{ key: string }>;
  loginOptions(): Promise<LoginOptions>;
  login(body: { webauthn: WebAuthnAssertion; client: 'mobile'; device_name?: string }): Promise<LoginResult>;
  refreshSession(refreshToken: string): Promise<LoginResult>;
  logout(): Promise<void>;
  passkeyRegisterOptions(): Promise<RegisterOptions>;
  passkeyRegister(body: { webauthn: WebAuthnAttestation; label: string }): Promise<{ credential_id: string; label: string }>;
  deviceRequest(body: DeviceRequestBody): Promise<DeviceRequest>;
  deviceRequestStatus(id: string, pollCode?: string): Promise<DeviceRequest>;
  /** Device-bound renewal (RFC 9449 DPoP proof in the `DPoP` header). */
  deviceToken(dpopProof: string, refreshToken: string): Promise<LoginResult>;
  /** Where the SSE stream lives and which bearer to send; undefined in demo mode (no stream). */
  eventsEndpoint(): { url: string; bearer: () => string | undefined; refresh?: () => Promise<string | undefined> } | undefined;
}

/** §3 codes and the §12.2 additions. Any other code is handled by its HTTP status class (§12.2). */
const KNOWN_CODES = new Set([
  'permission_denied',
  'stale_precondition',
  'expired',
  'conflict',
  'outcome_unknown',
  'not_found',
  'unauthenticated',
  'rate_limited',
  'unavailable',
  'payload_too_large',
  'policy_refused',
]);

function isErrorBody(v: unknown): v is ApiErrorBody {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as ApiErrorBody).error === 'string' &&
    typeof (v as ApiErrorBody).message === 'string'
  );
}

function codeForStatus(status: number): ApiError['code'] {
  switch (status) {
    case 401:
      return 'unauthenticated';
    case 403:
      return 'permission_denied';
    case 404:
      return 'not_found';
    case 409:
      return 'conflict';
    case 413:
      return 'payload_too_large';
    case 429:
      return 'rate_limited';
    case 503:
      return 'unavailable';
    default:
      return 'unknown';
  }
}

/** Turn a non-2xx answer into an ApiError; exported for the SSE transport. */
export function errorFrom(status: number, data: unknown, retryAfterHeader?: string | null): ApiError {
  const headerRetry = retryAfterHeader ? Number(retryAfterHeader) : NaN;
  if (isErrorBody(data)) {
    const code = KNOWN_CODES.has(data.error) ? (data.error as ApiError['code']) : codeForStatus(status);
    const retry = typeof data.retry_after_s === 'number' ? data.retry_after_s : Number.isFinite(headerRetry) ? headerRetry : undefined;
    // API.md §8.4 spelled the step-up signal as details[0].problem; §12.2 as reason. Accept both.
    const reason = data.reason ?? data.details?.[0]?.problem;
    return new ApiError(status, code, data.message, { reason, retryAfterS: retry });
  }
  return new ApiError(status, codeForStatus(status), `HTTP ${status}`, {
    retryAfterS: Number.isFinite(headerRetry) ? headerRetry : undefined,
  });
}

/**
 * Mobile addition: trim, drop trailing slashes, and require an absolute http(s) URL.
 * Throws a plain Error with a user-facing message otherwise.
 */
export function normalizeHubUrl(raw: string): string {
  const v = raw.trim().replace(/\/+$/, '');
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    throw new Error('Enter the hub address, for example https://onemind.local:8443');
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('The hub address must start with http:// or https://');
  return v;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

type Shape = 'object' | 'array' | 'any';

const enc = encodeURIComponent;

/** Real client: talks to the gateway over HTTP(S) with a bearer token. */
export class HttpApi implements OneMindApi {
  private readonly base: string;
  private readonly tokens: TokenSource;
  private readonly fetchFn: FetchLike;
  private readonly timeoutMs: number;
  private offsetMs: number | undefined;
  private renewing: Promise<string | undefined> | undefined;
  private featuresCache: Promise<Features> | undefined;

  // Mobile change: the hub URL is required (a phone has no same-origin hub), and
  // every request has a timeout, because a phone off the home network otherwise
  // waits for the OS TCP timeout (a minute or more) on an unreachable LAN address.
  constructor(opts: { token?: string; tokens?: TokenSource; baseUrl: string; fetchFn?: FetchLike; timeoutMs?: number }) {
    this.base = normalizeHubUrl(opts.baseUrl);
    const fixed = opts.token;
    this.tokens = opts.tokens ?? { current: () => fixed };
    this.fetchFn = opts.fetchFn ?? ((input, init) => fetch(input, init));
    this.timeoutMs = opts.timeoutMs ?? 10_000;
  }

  /** One renewal at a time, shared by every request that hit the same 401. */
  private renew(): Promise<string | undefined> {
    if (!this.tokens.refresh) return Promise.resolve(undefined);
    this.renewing ??= this.tokens.refresh().finally(() => {
      this.renewing = undefined;
    });
    return this.renewing;
  }

  /**
   * `shape` is what a 2xx body must be. Anything else (an HTML page from a proxy
   * or SPA fallback, an empty body, the wrong JSON type) is an error, not data.
   */
  private async req<T>(
    method: string,
    path: string,
    body?: unknown,
    shape: Shape = 'object',
    opts: { auth?: boolean; headers?: Record<string, string>; retried?: boolean } = {},
  ): Promise<T> {
    let res: Response;
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const timer = ctl ? setTimeout(() => ctl.abort(), this.timeoutMs) : undefined;
    const bearer = opts.auth === false ? undefined : this.tokens.current();
    try {
      res = await this.fetchFn(this.base + path, {
        signal: ctl?.signal,
        method,
        headers: {
          Accept: 'application/json',
          // §12.1: clients send the API major version they speak.
          'OneMind-API-Version': '1',
          ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...opts.headers,
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      if (ctl?.signal.aborted) throw new ApiError(0, 'network', `The hub did not answer within ${this.timeoutMs / 1000} s`);
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'Network error');
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
    // The hub stamps last_seen with its own clock; the Date header lets the UI
    // age it on that clock instead of the phone's (1 s resolution is enough
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
      const err = errorFrom(res.status, data, res.headers.get('Retry-After'));
      // A session token may have expired: renew once and repeat. A step-up refusal is not an expiry.
      if (err.code === 'unauthenticated' && err.reason !== 'step_up_required' && bearer && !opts.retried && this.tokens.refresh) {
        const fresh = await this.renew();
        if (fresh) return this.req<T>(method, path, body, shape, { ...opts, retried: true });
      }
      throw err;
    }
    if (res.status === 204 || shape === 'any') return data as T;
    const valid =
      shape === 'array' ? Array.isArray(data) : typeof data === 'object' && data !== null && !Array.isArray(data);
    if (!valid) throw new ApiError(res.status, 'unknown', 'Unexpected response from the hub');
    return data as T;
  }

  hubOffsetMs() {
    return this.offsetMs;
  }
  healthz() {
    return this.req<{ ok: boolean }>('GET', '/healthz', undefined, 'object', { auth: false });
  }
  instance() {
    return this.req<Instance>('GET', '/v1/instance');
  }
  nodes() {
    return this.req<NodeRecord[]>('GET', '/v1/nodes', undefined, 'array');
  }
  node(nodeId: string) {
    return this.req<NodeRecord>('GET', `/v1/nodes/${enc(nodeId)}`);
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
    return this.req<Action>('GET', `/v1/actions/${enc(id)}`);
  }
  approve(id: string, body?: ApproveBody) {
    const b = body && (body.plan_sha256 || body.webauthn) ? body : undefined;
    return this.req<Action>('POST', `/v1/actions/${enc(id)}/approve`, b);
  }
  deny(id: string, reason?: string) {
    return this.req<Action>('POST', `/v1/actions/${enc(id)}/deny`, reason ? { reason } : undefined);
  }

  features(): Promise<Features> {
    // /openapi.json is open (§3), so this works before sign-in. A failure means "assume v0", and is retried next time.
    this.featuresCache ??= this.req<unknown>('GET', '/openapi.json', undefined, 'object', { auth: false })
      .then((spec) => Features.fromOpenApi(spec))
      .catch(() => {
        this.featuresCache = undefined;
        return Features.none();
      });
    return this.featuresCache;
  }
  me() {
    return this.req<Me>('GET', '/v1/me');
  }
  approveOptions(id: string) {
    return this.req<ApproveOptions>('POST', `/v1/actions/${enc(id)}/approve-options`, {});
  }
  preview(id: string) {
    return this.req<{ plan: Plan; plan_sha256: string }>('GET', `/v1/actions/${enc(id)}/preview`);
  }
  notifications(q: { unread?: boolean; limit?: number } = {}) {
    const qs = new URLSearchParams();
    if (q.unread) qs.set('unread', 'true');
    qs.set('limit', String(q.limit ?? 100));
    return this.req<InboxItem[]>('GET', `/v1/notifications?${qs.toString()}`, undefined, 'array');
  }
  notification(id: string) {
    return this.req<InboxItem>('GET', `/v1/notifications/${enc(id)}`);
  }
  async markRead(id: string) {
    await this.req<unknown>('POST', `/v1/notifications/${enc(id)}/read`, undefined, 'any');
  }
  markAllRead() {
    return this.req<{ marked: number }>('POST', '/v1/notifications/read-all');
  }
  alerts(state?: 'open') {
    return this.req<AlertRecord[]>('GET', `/v1/alerts${state ? `?state=${state}` : ''}`, undefined, 'array');
  }
  ackAlert(id: string) {
    return this.req<AlertRecord>('POST', `/v1/alerts/${enc(id)}/ack`);
  }
  fixAlert(id: string) {
    return this.req<Action>('POST', `/v1/alerts/${enc(id)}/fix`, {});
  }
  pushRegister(req: PushRegistrationRequest) {
    return this.req<PushRegistration>('POST', '/v1/push/registrations', req);
  }
  pushRegistrations() {
    return this.req<PushRegistration[]>('GET', '/v1/push/registrations', undefined, 'array');
  }
  async pushUnregister(id: string) {
    await this.req<unknown>('DELETE', `/v1/push/registrations/${enc(id)}`, undefined, 'any');
  }
  vapidPublicKey() {
    return this.req<{ key: string }>('GET', '/v1/push/vapid-public-key');
  }
  loginOptions() {
    return this.req<LoginOptions>('POST', '/v1/auth/login/options', {}, 'object', { auth: false });
  }
  login(body: { webauthn: WebAuthnAssertion; client: 'mobile'; device_name?: string }) {
    return this.req<LoginResult>('POST', '/v1/auth/login', body, 'object', { auth: false });
  }
  refreshSession(refreshToken: string) {
    return this.req<LoginResult>('POST', '/v1/auth/refresh', { refresh_token: refreshToken }, 'object', { auth: false });
  }
  async logout() {
    await this.req<unknown>('POST', '/v1/auth/logout', undefined, 'any');
  }
  passkeyRegisterOptions() {
    return this.req<RegisterOptions>('POST', '/v1/auth/passkeys/register/options', {});
  }
  passkeyRegister(body: { webauthn: WebAuthnAttestation; label: string }) {
    return this.req<{ credential_id: string; label: string }>('POST', '/v1/auth/passkeys/register', body);
  }
  deviceRequest(body: DeviceRequestBody) {
    return this.req<DeviceRequest>('POST', '/v1/devices/requests', body);
  }
  deviceRequestStatus(id: string, pollCode?: string) {
    return this.req<DeviceRequest>('GET', `/v1/devices/requests/${enc(id)}`, undefined, 'object', {
      headers: pollCode ? { 'OneMind-Poll-Code': pollCode } : {},
    });
  }
  deviceToken(dpopProof: string, refreshToken: string) {
    return this.req<LoginResult>('POST', '/v1/devices/token', { refresh_token: refreshToken }, 'object', {
      auth: false,
      headers: { DPoP: dpopProof },
    });
  }
  eventsEndpoint() {
    return {
      url: `${this.base}/v1/events`,
      bearer: () => this.tokens.current(),
      refresh: this.tokens.refresh ? () => this.renew() : undefined,
    };
  }
  /** The absolute URL of a path on this hub (DPoP `htu`). */
  url(path: string): string {
    return this.base + path;
  }
}

// SPDX-License-Identifier: Apache-2.0
// The phone's API layer. Every JSON request goes out through the generated client's transport,
// `OneMind.call` from `@onemind/sdk` (CI-08, issue 233), so the phone and the dashboard share one
// client; `HttpApi.sdk` hands that client to screens that call generated paths directly. The phone keeps
// its own error mapping (ApiError), session renewal and response-shape checks on top. Binary transfers
// (tus uploads, downloads) stay on fetch: the JSON client cannot carry them.
// contract.ts checks the hand-written types in types.ts against the generated schema at compile time.
import { OneMind, NetworkError, type components } from '@onemind/sdk';
import { noteProtocol, PROTOCOL_HEADER, PROTOCOL_VERSION } from '../lib/protocol';
import {
  ApiError,
  type Action,
  type ActionRequest,
  type AlertRecord,
  type ApiErrorBody,
  type ApproveBody,
  type ApproverKey,
  type ApproveOptions,
  type AutomationRule,
  type AutomationRun,
  type AutomationState,
  type BackupDestination,
  type BackupRun,
  type BackupStatus,
  type CatalogApp,
  type DeviceRequest,
  type DeviceRequestBody,
  type FileEntry,
  type FileRoot,
  type FirstRunSettings,
  type FirstRunSettingsBody,
  type HomeBody,
  type HomeView,
  type InboxItem,
  type Instance,
  type FamilyProfile,
  type KillSwitch,
  type TokenInfo,
  type CreatedUser,
  type UserInfo,
  type LifecycleType,
  type LoginResult,
  type MeshView,
  type StatusView,
  type MonitoringSummary,
  type MyDeviceRemoved,
  type MyDevices,
  type NodeMetrics,
  type AppMetrics,
  type OsUpdateHistory,
  type OsUpdateStatus,
  type SystemControlType,
  type SystemPlanPreview,
  type Me,
  type GeoSite,
  type MigratePlan,
  type NodeRecord,
  type Plan,
  type PlanPreview,
  type PushRegistration,
  type PushRegistrationRequest,
  type AppSecrets,
  type SecretsPublicKey,
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
  /** #702: register this phone's approval key. */
  approverKeys: 'POST /v1/auth/approver-keys',
  /** Not in §12.6 (it returns a refresh_token but names no route); used only when the gateway lists it. */
  authRefresh: 'POST /v1/auth/refresh',
  deviceRequest: 'POST /v1/devices/requests',
  /** The person's own devices (issue 716): used instead of /v1/devices/requests once the gateway lists it. */
  meDevices: 'POST /v1/me/devices',
  deviceToken: 'POST /v1/devices/token',
  /** §12.41 (owner only). */
  onboardingSettings: 'GET /v1/onboarding/settings',
  tips: 'GET /v1/tips',
  /** UMB-P07: the person's own Home (appearance, layout, dock) kept on the hub. */
  homeGet: 'GET /v1/me/home',
  /** §12.40. */
  appPlan: 'GET /v1/apps/{}/plan',
  backupStatus: 'GET /v1/backups/status',
  backupDestinations: 'GET /v1/backups/destinations',
  backupRuns: 'GET /v1/backups/runs',
  backupRequestRun: 'POST /v1/backups/runs',
  backupVerify: 'POST /v1/backups/verify',
  automationRules: 'GET /v1/automation/rules',
  automationState: 'GET /v1/automation/state',
  filesRoots: 'GET /v1/files/roots',
  filesList: 'GET /v1/files/list',
  filesDownload: 'GET /v1/files/download',
  filesVersions: 'GET /v1/files/versions',
  filesUploads: 'POST /v1/files/uploads',
  migratePlans: 'GET /v1/migrate/plans',
  /** §12.6 users (owner), FAM-01 family limits, CORE-SEC-6 agent kill switch. */
  users: 'GET /v1/users',
  usersCreate: 'POST /v1/users',
  usersUpdate: 'PATCH /v1/users/{}',
  familyProfile: 'GET /v1/family/profiles/{}',
  tokens: 'GET /v1/tokens',
  killSwitch: 'GET /v1/agents/kill-switch',
  killSwitchSet: 'PUT /v1/agents/kill-switch',
  osUpdates: 'GET /v1/os/updates',
  osUpdateHistory: 'GET /v1/os/updates/history',
  monitoringSummary: 'GET /v1/monitoring/summary',
  nodeMetrics: 'GET /v1/nodes/{}/metrics',
  appMetrics: 'GET /v1/apps/{}/metrics',
  mesh: 'GET /v1/mesh',
  /** Phone Map tab (#656): the sites the plan is framed on. */
  sites: 'GET /v1/sites',
  /** Health of every source at a glance. */
  status: 'GET /v1/status',
  /**
   * Never in /openapi.json, so System controls stays hidden: the hub has no plan preview for restart /
   * shut down / troubleshoot. It serves `GET /v1/system/controls` and `POST /v1/system/actions` instead,
   * a different flow (confirm phrase, no plan hash); `HttpApi.systemPlan` sends nothing.
   */
  systemPlan: 'GET /v1/system/plan',
  myDevices: 'GET /v1/me/devices',
  myDeviceRemove: 'DELETE /v1/me/devices/{}',
  /** #528: an install's declared secrets (names and set flags only) and the box key the form is sealed to. */
  appSecrets: 'GET /v1/apps/{}/secrets',
  secretsPublicKey: 'GET /v1/secrets/public-key',
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

/** `POST /v1/auth/login` with a passkey. `client: 'app'` asks for a bearer and a refresh token instead of a cookie. */
export interface LoginBody {
  passkey: WebAuthnAssertion;
  client: 'app';
  client_name?: string;
  /** This app install (#715, lib/install.ts): My devices groups this sign-in with the install's passkeys and push. */
  install_id?: string;
}

/** WebAuthn options as the gateway sends them: bare JSON, or wrapped in `publicKey` (both are common). */
export type LoginOptions = Partial<WebAuthnRequestOptions> & { publicKey?: Partial<WebAuthnRequestOptions> };
export type RegisterOptions = Partial<WebAuthnCreationOptions> & { publicKey?: Partial<WebAuthnCreationOptions> };

/**
 * Everything the phone may ask the hub: the §3 routes plus the §12 routes it uses.
 * The phone never decides anything; every write is a request or a decision the gateway checks.
 */
function readUploadOffset(res: Response): number {
  const header = res.headers.get('Upload-Offset');
  const offset = Number(header);
  if (!header || !/^\d+$/.test(header) || !Number.isSafeInteger(offset)) {
    throw new ApiError(res.status, 'unknown', 'The hub sent no valid Upload-Offset.');
  }
  return offset;
}

/** A file-backed PATCH handed to the OS, with the same origin check and token renewal as fetch. */
export type TusTransport = (url: string, headers: Record<string, string>, bytes: Uint8Array) => Promise<Response>;

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
  /** Field names as the hub's identity module reads them: `passkey`, `client: 'app'` (bearer + refresh), `client_name`. */
  login(body: LoginBody): Promise<LoginResult>;
  refreshSession(refreshToken: string): Promise<LoginResult>;
  logout(): Promise<void>;
  passkeyRegisterOptions(): Promise<RegisterOptions>;
  passkeyRegister(body: { credential: WebAuthnAttestation; label: string; install_id?: string }): Promise<{ credential_id: string; label: string }>;
  /** #702 (optional: only the live client has them; feature-detect with OP.approverKeys). */
  approverKeyRegister?(body: { public_key: string; label: string; key_kind: 'hardware-reported' | 'software' }): Promise<ApproverKey>;
  approverKeyRevoke?(keyId: string): Promise<void>;
  /** #528 (optional: only the live client has them; feature-detect with OP.appSecrets and OP.secretsPublicKey). */
  appSecrets?(appId: string): Promise<AppSecrets>;
  secretsPublicKey?(): Promise<SecretsPublicKey>;
  /** `me`: the newer `/v1/me/devices` routes (only when `features()` lists OP.meDevices). */
  deviceRequest(body: DeviceRequestBody, o?: { me?: boolean }): Promise<DeviceRequest>;
  deviceRequestStatus(id: string, pollCode?: string, o?: { me?: boolean }): Promise<DeviceRequest>;
  /** Device-bound renewal (RFC 9449 DPoP proof in the `DPoP` header). */
  deviceToken(dpopProof: string, refreshToken: string): Promise<LoginResult>;

  // §12.41 first-run settings, owner only (403 for everyone else).
  /** UMB-P07: the person's Home and the ETag to send back with the next save. */
  home(): Promise<{ home: HomeView; etag: string }>;
  saveHome(doc: HomeBody, etag: string): Promise<{ home: HomeView; etag: string }>;
  onboardingSettings(): Promise<FirstRunSettings>;
  /** Full replacement; the hub validates the name, zone and destination (422) and writes nothing on a refusal. */
  saveOnboardingSettings(body: FirstRunSettingsBody): Promise<FirstRunSettings>;
  // §12.40 app lifecycle. `appPlan` files nothing; the request goes through `createAction` and waits for an owner.
  appPlan(appId: string, type: LifecycleType | 'app.install'): Promise<PlanPreview>;
  // §12.12 backups. Both writes only FILE a request (`approve: false` is always sent); an owner approves it.
  backupStatus(): Promise<BackupStatus>;
  backupDestinations(): Promise<BackupDestination[]>;
  backupRuns(): Promise<BackupRun[]>;
  requestBackupRun(body: { reason?: string; destination_id?: string; idempotencyKey: string }): Promise<Action>;
  requestBackupVerify(body: { reason?: string; idempotencyKey: string }): Promise<Action>;
  // §12.17 automation. Disabling a rule and pausing are always safe; enabling and resuming are owner-only.
  automationState(): Promise<AutomationState>;
  automationRules(): Promise<AutomationRule[]>;
  automationRuns(): Promise<AutomationRun[]>;
  setRuleEnabled(id: string, enabled: boolean): Promise<AutomationRule>;
  setAutomationPaused(paused: boolean, reason?: string): Promise<AutomationState>;
  // Files and migration, read only on the phone.
  filesRoots(): Promise<FileRoot[]>;
  filesList(root: string, path: string): Promise<FileEntry[]>;
  filesVersions(root: string, path: string): Promise<components['schemas']['FileVersions']>;
  /** Where and how to fetch one file's bytes (the native layer streams it to disk; the token never goes to another origin). */
  filesDownloadRequest(root: string, path: string): { url: string; headers: Record<string, string> };
  /** tus 1.0.0 (docs/leap/core/FILES.md section 3): create the upload; returns its absolute URL. 403 no write access, 409 name taken, 413 quota. */
  filesUploadCreate(m: { root: string; path: string; name: string; size: number; sha256?: string }): Promise<string>;
  /** `HEAD` the upload: how many bytes the hub holds (resume point). */
  filesUploadOffset(url: string): Promise<number>;
  /** `PATCH` one chunk at `offset`; returns the new offset and, on the last chunk, the hub's whole-file sha256. */
  filesUploadChunk(url: string, offset: number, bytes: Uint8Array, transport?: TusTransport): Promise<{ offset: number; sha256?: string }>;
  migratePlans(): Promise<MigratePlan[]>;
  // People and agents. Writes are owner-only on the hub, which also asks for a fresh passkey (`step_up_required`).
  users(): Promise<UserInfo[]>;
  createUser(body: { display_name: string; role: string }): Promise<CreatedUser>;
  setUserRole(id: string, role: string): Promise<UserInfo>;
  familyProfile(id: string): Promise<FamilyProfile>;
  apiTokens(): Promise<TokenInfo[]>;
  killSwitch(): Promise<KillSwitch>;
  setKillSwitch(on: boolean, reason?: string): Promise<KillSwitch>;
  // System screens (read only, except that an install or a control is filed as a request).
  osUpdates(): Promise<OsUpdateStatus>;
  osUpdateHistory(): Promise<OsUpdateHistory>;
  monitoringSummary(): Promise<MonitoringSummary>;
  nodeMetrics(nodeId: string, window?: string): Promise<NodeMetrics>;
  appMetrics(appId: string): Promise<AppMetrics>;
  mesh(): Promise<MeshView>;
  sites(): Promise<GeoSite[]>;
  status(): Promise<StatusView>;
  systemPlan(type: SystemControlType): Promise<SystemPlanPreview>;
  // #715 My devices: the caller's own devices; removing one revokes everything it holds (a fresh passkey once passkeys are on).
  myDevices(): Promise<MyDevices>;
  removeMyDevice(id: string): Promise<MyDeviceRemoved>;
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
  'upgrade_required',
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
export function errorFrom(status: number, data: unknown, retryAfterHeader?: string | null, dpopNonce?: string | null): ApiError {
  const headerRetry = retryAfterHeader ? Number(retryAfterHeader) : NaN;
  const nonce = dpopNonce ?? undefined;
  if (isErrorBody(data)) {
    const code = KNOWN_CODES.has(data.error) ? (data.error as ApiError['code']) : codeForStatus(status);
    const retry = typeof data.retry_after_s === 'number' ? data.retry_after_s : Number.isFinite(headerRetry) ? headerRetry : undefined;
    // API.md §8.4 spelled the step-up signal as details[0].problem; §12.2 as reason. Accept both.
    const reason = data.reason ?? data.details?.[0]?.problem;
    return new ApiError(status, code, data.message, { reason, retryAfterS: retry, dpopNonce: nonce });
  }
  return new ApiError(status, codeForStatus(status), `HTTP ${status}`, {
    retryAfterS: Number.isFinite(headerRetry) ? headerRetry : undefined,
    dpopNonce: nonce,
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

/** One request as `OneMind.call` takes it; the transport passes DELETE and PATCH through as well. */
type SdkRequest = Parameters<OneMind['call']>[0];

/** Ties a request the SDK sends back to the HttpApi call that asked for it; removed before it leaves the phone. */
const CALL_HEADER = 'X-OneMind-Phone-Call';

/** What came back for one call, read by the transport before the SDK parses it. */
interface Exchange {
  auth: boolean;
  thrown?: unknown;
  res?: { ok: boolean; status: number; headers: Headers; data: unknown };
}

/** The generated client behind an API object, or undefined for one that does not talk to a hub. */
export function sdkOf(api: OneMindApi): OneMind | undefined {
  return api instanceof HttpApi ? api.sdk : undefined;
}

/** Real client: talks to the gateway over HTTP(S) with a bearer token, through `@onemind/sdk`. */
export class HttpApi implements OneMindApi {
  /** The generated gateway client on the same hub, token and timeout (no retries: the phone shows the error). */
  readonly sdk: OneMind;
  private readonly base: string;
  private readonly tokens: TokenSource;
  private readonly fetchFn: FetchLike;
  private readonly timeoutMs: number;
  private offsetMs: number | undefined;
  private renewing: Promise<string | undefined> | undefined;
  private featuresCache: Promise<Features> | undefined;
  private readonly exchanges = new Map<string, Exchange>();
  private seq = 0;

  // Mobile change: the hub URL is required (a phone has no same-origin hub), and
  // every request has a timeout, because a phone off the home network otherwise
  // waits for the OS TCP timeout (a minute or more) on an unreachable LAN address.
  constructor(opts: { token?: string; tokens?: TokenSource; baseUrl: string; fetchFn?: FetchLike; timeoutMs?: number }) {
    this.base = normalizeHubUrl(opts.baseUrl);
    const fixed = opts.token;
    this.tokens = opts.tokens ?? { current: () => fixed };
    this.fetchFn = opts.fetchFn ?? ((input, init) => fetch(input, init));
    this.timeoutMs = opts.timeoutMs ?? 10_000;
    this.sdk = new OneMind({
      baseUrl: this.base,
      token: { token: () => this.tokens.current() ?? '' },
      timeoutMs: this.timeoutMs,
      retries: 1,
      fetch: ((input: string, init?: RequestInit) => this.send(input, init)) as unknown as typeof fetch,
      // A hub on the home network over plain http is the normal first run (app.json allows cleartext).
      onWarning: () => undefined,
    });
  }

  /**
   * The fetch the SDK sends through. It adds what the phone sends on every request, drops the bearer
   * on the calls that must go without one, learns the hub clock, and keeps the answer for `req`.
   */
  private async send(url: string, init: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
    const ex = this.exchanges.get(headers[CALL_HEADER] ?? '');
    delete headers[CALL_HEADER];
    if (ex && !ex.auth) delete headers.Authorization;
    // §12.1: clients send the API major version they speak.
    headers['OneMind-API-Version'] = '1';
    // The phone's own generation, not the SDK's fixed one: a lab "older app" build
    // (EXPO_PUBLIC_ONEMIND_PROTOCOL) must declare one version on JSON calls, transfers and events alike.
    headers[PROTOCOL_HEADER] = String(PROTOCOL_VERSION);
    let res: Response;
    try {
      res = await this.fetchFn(url, { ...init, headers });
    } catch (e) {
      if (ex) ex.thrown = e;
      throw e;
    }
    // The hub stamps last_seen with its own clock; the Date header lets the UI
    // age it on that clock instead of the phone's (1 s resolution is enough
    // for the 30 s / 120 s thresholds).
    const hubDate = Date.parse(res.headers.get('Date') ?? '');
    if (!Number.isNaN(hubDate)) this.offsetMs = hubDate - Date.now();
    noteProtocol(res.headers);
    const text = await res.text();
    let data: unknown = undefined;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = undefined;
      }
    }
    if (ex) ex.res = { ok: res.ok, status: res.status, headers: res.headers, data };
    // The body was read once here; the SDK reads this copy.
    return { ok: res.ok, status: res.status, headers: res.headers, text: async () => text } as Response;
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
    opts: { auth?: boolean; headers?: Record<string, string>; retried?: boolean; onHeaders?: (h: Headers) => void } = {},
  ): Promise<T> {
    const bearer = opts.auth === false ? undefined : this.tokens.current();
    const id = String(++this.seq);
    const ex: Exchange = { auth: opts.auth !== false };
    this.exchanges.set(id, ex);
    let failure: unknown;
    try {
      const sdkReq = { method, path, body, retry: false, headers: { ...opts.headers, [CALL_HEADER]: id } } as SdkRequest;
      await this.sdk.call<unknown>(sdkReq);
    } catch (e) {
      // The SDK throws for every non-2xx answer and for a 2xx without JSON; the phone decides from the answer itself.
      failure = e;
    } finally {
      this.exchanges.delete(id);
    }
    const res = ex.res;
    if (!res) {
      if (failure instanceof NetworkError && failure.timedOut) throw new ApiError(0, 'network', `The hub did not answer within ${this.timeoutMs / 1000} s`);
      const cause = ex.thrown ?? failure;
      throw new ApiError(0, 'network', cause instanceof Error ? cause.message : 'Network error');
    }
    opts.onHeaders?.(res.headers);
    const data = res.data;
    if (!res.ok) {
      const err = errorFrom(res.status, data, res.headers.get('Retry-After'), res.headers.get('DPoP-Nonce'));
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
    const b = body && (body.plan_sha256 || body.webauthn || body.device_signature || body.sealed) ? body : undefined;
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
  login(body: LoginBody) {
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
  passkeyRegister(body: { credential: WebAuthnAttestation; label: string; install_id?: string }) {
    return this.req<{ credential_id: string; label: string }>('POST', '/v1/auth/passkeys/register', body);
  }
  approverKeyRegister(body: { public_key: string; label: string; key_kind: 'hardware-reported' | 'software' }) {
    return this.req<ApproverKey>('POST', '/v1/auth/approver-keys', body);
  }
  appSecrets(appId: string) {
    return this.req<AppSecrets>('GET', `/v1/apps/${enc(appId)}/secrets`);
  }
  secretsPublicKey() {
    return this.req<SecretsPublicKey>('GET', '/v1/secrets/public-key');
  }
  async approverKeyRevoke(keyId: string) {
    await this.req<unknown>('DELETE', `/v1/auth/approver-keys/${enc(keyId)}`, undefined, 'any');
  }
  deviceRequest(body: DeviceRequestBody, o: { me?: boolean } = {}) {
    return this.req<DeviceRequest>('POST', o.me ? '/v1/me/devices' : '/v1/devices/requests', body);
  }
  deviceRequestStatus(id: string, pollCode?: string, o: { me?: boolean } = {}) {
    return this.req<DeviceRequest>('GET', `${o.me ? '/v1/me/devices' : '/v1/devices/requests'}/${enc(id)}`, undefined, 'object', {
      headers: pollCode ? { 'OneMind-Poll-Code': pollCode } : {},
    });
  }
  deviceToken(dpopProof: string, refreshToken: string) {
    return this.req<LoginResult>('POST', '/v1/devices/token', { refresh_token: refreshToken }, 'object', {
      auth: false,
      headers: { DPoP: dpopProof },
    });
  }
  async home() {
    let etag = '';
    const home = await this.req<HomeView>('GET', '/v1/me/home', undefined, 'object', { onHeaders: (h) => void (etag = h.get('ETag') ?? '') });
    return { home, etag };
  }
  async saveHome(doc: HomeBody, etag: string) {
    let next = '';
    const home = await this.req<HomeView>('PUT', '/v1/me/home', doc, 'object', {
      headers: { 'If-Match': etag },
      onHeaders: (h) => void (next = h.get('ETag') ?? ''),
    });
    return { home, etag: next };
  }
  onboardingSettings() {
    return this.req<FirstRunSettings>('GET', '/v1/onboarding/settings');
  }
  saveOnboardingSettings(body: FirstRunSettingsBody) {
    return this.req<FirstRunSettings>('PUT', '/v1/onboarding/settings', body);
  }
  appPlan(appId: string, type: LifecycleType | 'app.install') {
    return this.req<PlanPreview>('GET', `/v1/apps/${enc(appId)}/plan?type=${enc(type)}`);
  }
  backupStatus() {
    return this.req<BackupStatus>('GET', '/v1/backups/status');
  }
  backupDestinations() {
    return this.req<BackupDestination[]>('GET', '/v1/backups/destinations', undefined, 'array');
  }
  backupRuns() {
    return this.req<BackupRun[]>('GET', '/v1/backups/runs', undefined, 'array');
  }
  // `approve: false` is spelled out: a request from the phone never approves itself (§12.12).
  requestBackupRun(body: { reason?: string; destination_id?: string; idempotencyKey: string }) {
    const { idempotencyKey, ...rest } = body;
    return this.req<Action>('POST', '/v1/backups/runs', { scope: 'box', ...rest, approve: false }, 'object', {
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  }
  requestBackupVerify(body: { reason?: string; idempotencyKey: string }) {
    const { idempotencyKey, ...rest } = body;
    return this.req<Action>('POST', '/v1/backups/verify', { ...rest, approve: false }, 'object', {
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  }
  automationState() {
    return this.req<AutomationState>('GET', '/v1/automation/state');
  }
  automationRules() {
    return this.req<AutomationRule[]>('GET', '/v1/automation/rules', undefined, 'array');
  }
  automationRuns() {
    return this.req<AutomationRun[]>('GET', '/v1/automation/runs', undefined, 'array');
  }
  setRuleEnabled(id: string, enabled: boolean) {
    return this.req<AutomationRule>('POST', `/v1/automation/rules/${enc(id)}/${enabled ? 'enable' : 'disable'}`, undefined);
  }
  setAutomationPaused(paused: boolean, reason?: string) {
    return this.req<AutomationState>('POST', `/v1/automation/${paused ? 'pause' : 'resume'}`, reason ? { reason } : {});
  }
  filesRoots() {
    return this.req<FileRoot[]>('GET', '/v1/files/roots', undefined, 'array');
  }
  filesList(root: string, path: string) {
    return this.req<FileEntry[]>('GET', `/v1/files/list?root=${enc(root)}&path=${enc(path)}&limit=200`, undefined, 'array');
  }
  filesVersions(root: string, path: string) {
    return this.req<components['schemas']['FileVersions']>('GET', `/v1/files/versions?root=${enc(root)}&path=${enc(path)}`);
  }
  filesDownloadRequest(root: string, path: string) {
    const bearer = this.tokens.current();
    return {
      url: `${this.base}/v1/files/download?root=${enc(root)}&path=${enc(path)}`,
      headers: { 'OneMind-API-Version': '1', [PROTOCOL_HEADER]: String(PROTOCOL_VERSION), ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
    };
  }
  /** One tus request. Not `req`: tus answers with headers and no JSON, and the location is an absolute URL on the hub. */
  private async tus(method: string, url: string, headers: Record<string, string>, body?: Uint8Array, retried = false, transport?: TusTransport): Promise<Response> {
    if (url !== this.base && !url.startsWith(this.base + '/')) throw new ApiError(0, 'unknown', 'The hub sent an upload address on another origin');
    const bearer = this.tokens.current();
    const ctl = !transport && typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const timer = ctl ? setTimeout(() => ctl.abort(), Math.max(this.timeoutMs, 60_000)) : undefined;
    const requestHeaders = { 'OneMind-API-Version': '1', [PROTOCOL_HEADER]: String(PROTOCOL_VERSION), 'Tus-Resumable': '1.0.0', ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}), ...headers };
    let res: Response;
    try {
      res = transport && body ? await transport(url, requestHeaders, body) : await this.fetchFn(url, {
        signal: ctl?.signal, method, headers: requestHeaders, body: body as unknown as BodyInit | undefined,
      });
    } catch (e) {
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'Network error');
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
    if (res.ok) return res;
    let data: unknown;
    try {
      data = JSON.parse(await res.text());
    } catch {
      data = undefined;
    }
    const err = errorFrom(res.status, data, res.headers.get('Retry-After'), res.headers.get('DPoP-Nonce'));
    if (err.code === 'unauthenticated' && err.reason !== 'step_up_required' && bearer && !retried && this.tokens.refresh && (await this.renew())) {
      return this.tus(method, url, headers, body, true, transport);
    }
    throw err;
  }
  async filesUploadCreate(m: { root: string; path: string; name: string; size: number; sha256?: string }) {
    const b64 = (v: string) => btoa(String.fromCharCode(...new TextEncoder().encode(v)));
    const pairs: [string, string][] = [['filename', m.name], ['root', m.root], ['path', m.path]];
    if (m.sha256) pairs.push(['sha256', m.sha256]);
    const meta = pairs.map(([k, v]) => `${k} ${b64(v)}`).join(',');
    const res = await this.tus('POST', `${this.base}/v1/files/uploads`, { 'Upload-Length': String(m.size), 'Upload-Metadata': meta });
    const loc = res.headers.get('Location');
    if (!loc) throw new ApiError(res.status, 'unknown', 'The hub did not return an upload address');
    return new URL(loc, this.base + '/').toString();
  }
  async filesUploadOffset(url: string) {
    const res = await this.tus('HEAD', url, {});
    return readUploadOffset(res);
  }
  async filesUploadChunk(url: string, offset: number, bytes: Uint8Array, transport?: TusTransport) {
    const res = await this.tus('PATCH', url, { 'Upload-Offset': String(offset), 'Content-Type': 'application/offset+octet-stream' }, bytes, false, transport);
    return { offset: readUploadOffset(res), sha256: res.headers.get('OneMind-File-Sha256') ?? undefined };
  }
  migratePlans() {
    return this.req<MigratePlan[]>('GET', '/v1/migrate/plans', undefined, 'array');
  }
  users() {
    return this.req<UserInfo[]>('GET', '/v1/users', undefined, 'array');
  }
  createUser(body: { display_name: string; role: string }) {
    return this.req<CreatedUser>('POST', '/v1/users', body);
  }
  setUserRole(id: string, role: string) {
    return this.req<UserInfo>('PATCH', `/v1/users/${enc(id)}`, { role });
  }
  familyProfile(id: string) {
    return this.req<FamilyProfile>('GET', `/v1/family/profiles/${enc(id)}`);
  }
  apiTokens() {
    return this.req<TokenInfo[]>('GET', '/v1/tokens', undefined, 'array');
  }
  killSwitch() {
    return this.req<KillSwitch>('GET', '/v1/agents/kill-switch');
  }
  setKillSwitch(on: boolean, reason?: string) {
    return this.req<KillSwitch>('PUT', '/v1/agents/kill-switch', reason ? { on, reason } : { on });
  }
  osUpdates() {
    return this.req<OsUpdateStatus>('GET', '/v1/os/updates');
  }
  osUpdateHistory() {
    return this.req<OsUpdateHistory>('GET', '/v1/os/updates/history');
  }
  monitoringSummary() {
    return this.req<MonitoringSummary>('GET', '/v1/monitoring/summary');
  }
  nodeMetrics(nodeId: string, window = '1h') {
    return this.req<NodeMetrics>('GET', `/v1/nodes/${enc(nodeId)}/metrics?window=${enc(window)}`);
  }
  appMetrics(appId: string) {
    return this.req<AppMetrics>('GET', `/v1/apps/${enc(appId)}/metrics`);
  }
  mesh() {
    return this.req<MeshView>('GET', '/v1/mesh');
  }
  sites() {
    return this.req<GeoSite[]>('GET', '/v1/sites', undefined, 'array');
  }
  status() {
    return this.req<StatusView>('GET', '/v1/status');
  }
  /** Hidden (see `OP.systemPlan`): the hub serves no system plan preview, so nothing is sent. */
  systemPlan(type: SystemControlType): Promise<SystemPlanPreview> {
    return Promise.reject(new ApiError(404, 'not_found', `This hub has no plan preview for ${type}.`));
  }
  myDevices() {
    return this.req<MyDevices>('GET', '/v1/me/devices');
  }
  removeMyDevice(id: string) {
    return this.req<MyDeviceRemoved>('DELETE', `/v1/me/devices/${enc(id)}`);
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

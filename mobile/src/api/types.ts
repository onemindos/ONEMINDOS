// SPDX-License-Identifier: Apache-2.0
// Copied from dashboard/src/api/types.ts (feat/gwmcp, commit 951470f) so the phone app and the
// dashboard speak the same contract types. Keep the two in sync; mobile changes noted inline.
// Types for the proof-of-concept v0 contract (sdk/contracts/poc-v0.md).
// Section numbers below refer to that file.

/** §2 `board` values. */
export type Board =
  | 'x86_64-efi'
  | 'arm64-efi'
  | 'rpi5'
  | 'jetson-orin'
  | 'vm'
  | 'vm-do'
  | 'unknown';

export type SecureBoot = 'enabled' | 'disabled' | 'unsupported' | 'unknown';

/** §2 node heartbeat, schema `onemind.node.status/v1`. */
export interface NodeHeartbeat {
  schema: 'onemind.node.status/v1';
  node_id: string;
  hostname: string;
  role: 'hub' | 'node';
  board: Board;
  arch: string;
  os: { id: string; version_id: string; pretty: string };
  kernel: string;
  cpu_model: string;
  cpus: number;
  mem_total_mb: number;
  mem_available_mb: number;
  disk_total_gb: number;
  disk_free_gb: number;
  tpm2: boolean;
  secure_boot: SecureBoot;
  k3s: { present: boolean; role: string | null; ready: boolean };
  rauc: { present: boolean; booted_slot: string | null; slots: unknown[] };
  gpu: { nvidia: boolean; model: string | null };
  uptime_s: number;
  agent_version: string;
  observed_at: string;
  /**
   * Mobile addition: OS update state, optional and additive (updater branch,
   * internal/heartbeat `update,omitempty`; not yet in contract §2). Absent on most nodes.
   */
  update?: NodeUpdate;
}

export interface NodeUpdate {
  channel: string;
  current_version: string;
  available_version: string | null;
  state: string;
  last_check: string | null;
  last_result: string;
}

/** §3 freshness computed by the gateway: stale after 30 s, offline after 120 s. */
export type NodeStatus = 'online' | 'stale' | 'offline';

/** §3 `GET /v1/nodes` item: heartbeat plus `status` and `last_seen`. */
export interface NodeRecord extends NodeHeartbeat {
  status: NodeStatus;
  last_seen: string;
}

/** §3 `GET /v1/instance`. */
export interface Instance {
  name: string;
  version: string;
  hub_node_id: string;
  /** §12.1 additions. */
  api?: { version: string; min_client?: string };
  features?: string[];
}

/** §9.3 `metadata.links`; the gateway passes only absolute http(s) URLs, else null. */
export interface AppLinks {
  docs: string | null;
  github: string | null;
  website: string | null;
  support: string | null;
}

/** §9.3 tier, set by the app CI gate; null when the manifest has none yet. */
export type AppTier = 'verified' | 'community' | 'blocked';

/** §11.1 scan record as summarised in the catalog (§11.4). */
export interface ScanSummary {
  scanned_at: string;
  result: 'pass' | 'fail';
}

/** §3 `GET /v1/apps` item, built from §4 `onemind.app.yaml`, plus the §11.4 fields. */
export interface CatalogApp {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  icon: string;
  license: string;
  source: string;
  archs: string[];
  requires: { gpu?: boolean; minMemoryMb?: number };
  web_port: number | null;
  installed: boolean;
  status: string;
  links: AppLinks;
  tier: AppTier | null;
  /** Last scan, or null when the app has never been scanned (or its record is unreadable). */
  scan: ScanSummary | null;
}

/** §3 types the phone itself requests; §12.5 adds many more, which the phone shows but never invents. */
export type ActionType = 'app.install' | 'app.remove' | (string & {});

/** §3 action states. */
export type ActionState =
  | 'requested'
  | 'awaiting_approval'
  | 'accepted'
  | 'dispatched'
  | 'succeeded'
  | 'failed'
  | 'outcome_unknown'
  | 'expired'
  | 'cancelled';

/** §3 kinds plus the §12.1 additions (`plugin`, `automation`, `node`). */
export type PrincipalKind = 'person' | 'agent' | 'plugin' | 'automation' | 'node';
/** §12.6 adds `child`; unknown roles are treated as the least privileged. */
export type PrincipalRole = 'owner' | 'adult' | 'guest' | 'child' | 'agent';

/** §3 tokens map to principals `{id, kind, role}`. */
export interface Principal {
  id: string;
  kind: PrincipalKind;
  role: PrincipalRole;
}

/**
 * Mobile change: who requested or decided an action. The gateway stores
 * `requested_by` as `{id, kind}` only (core ledger), so `role` is optional here.
 */
export interface PrincipalRef {
  id: string;
  kind: PrincipalKind;
  role?: PrincipalRole;
}

/** §3 `POST /v1/actions` body. */
export interface ActionRequest {
  type: ActionType;
  /** §3 `{app_id}`; §12.5 types carry other params, shown to the owner exactly as stored. */
  params: { app_id?: string; [key: string]: unknown };
  idempotency_key: string;
  expires_at: string;
}

/**
 * Executor outcome attached to a finished action. Not named in §3; this is what
 * the wave-1 gateway returns (`{outcome, message, steps}`), see README "Known gaps".
 */
export interface ActionResult {
  outcome: string;
  message: string;
  steps?: unknown[];
}

/**
 * §3 action as returned by the gateway.
 * The contract names the request fields and the states but not the full response
 * shape. `requested_by`, `created_at` and `updated_at` are this dashboard's
 * expectation (see README "Known gaps"); every one is optional so the UI degrades
 * to "unknown" instead of crashing if the gateway names them differently.
 */
export interface Action extends ActionRequest {
  id: string;
  state: ActionState;
  requested_by?: PrincipalRef;
  created_at?: string;
  updated_at?: string;
  decided_by?: PrincipalRef | null;
  decided_at?: string | null;
  result?: ActionResult | null;
  // §12.4 additions, all optional for v0 gateways.
  risk?: Risk;
  /** Why the requester asked (≤ 500 chars). From an agent this is untrusted text. */
  reason?: string | null;
  target?: { kind: string; id: string; node_id?: string } | null;
  plan?: Plan | null;
  plan_sha256?: string | null;
  /** `person:<id>` or `policy:<id>@<rev>` (§12.1). */
  approved_by?: string | null;
  approved_via?: 'dashboard' | 'phone' | 'cli' | 'policy' | 'console' | null;
  approval?: 'passkey' | 'token' | 'policy' | 'console' | null;
  hold?: { window_id: string; until: string } | null;
}

/** §12.3 risk classes. */
export type Risk = 'read' | 'write' | 'sensitive' | 'destructive' | 'actuate';

/** §12.4 plan, rendered by the gateway at request time; what the owner approves is this plan. */
export interface Plan {
  summary?: string;
  objects?: unknown[];
  images?: unknown[];
  volumes?: unknown[];
  nodes?: unknown[];
  warnings?: string[];
}

/** §12.4 `POST /v1/actions/{id}/approve-options`. `publicKey`/`rpId`/`allowCredentials` are optional extras (see lib/webauthn). */
export interface ApproveOptions {
  challenge: string;
  action_sha256: string;
  plan_sha256: string;
  expires_at: string;
  rpId?: string;
  allowCredentials?: Array<{ id: string; type: 'public-key'; transports?: string[] }>;
  userVerification?: 'required' | 'preferred' | 'discouraged';
  publicKey?: Partial<WebAuthnRequestOptions>;
}

/** The assertion fields the gateway checks (§12.4 approve body `webauthn`). Base64url strings. */
export interface WebAuthnAssertion {
  id: string;
  clientDataJSON: string;
  authenticatorData: string;
  signature: string;
  userHandle?: string;
}

export interface WebAuthnAttestation {
  id: string;
  clientDataJSON: string;
  attestationObject: string;
  transports?: string[];
}

/** WebAuthn PublicKeyCredentialRequestOptions in JSON form (base64url binary fields). */
export interface WebAuthnRequestOptions {
  challenge: string;
  rpId: string;
  timeout?: number;
  allowCredentials?: Array<{ id: string; type: 'public-key'; transports?: string[] }>;
  userVerification?: 'required' | 'preferred' | 'discouraged';
}

/** WebAuthn PublicKeyCredentialCreationOptions in JSON form. */
export interface WebAuthnCreationOptions {
  challenge: string;
  rp: { id: string; name: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: Array<{ type: 'public-key'; alg: number }>;
  timeout?: number;
  excludeCredentials?: Array<{ id: string; type: 'public-key'; transports?: string[] }>;
  authenticatorSelection?: {
    authenticatorAttachment?: 'platform' | 'cross-platform';
    residentKey?: 'discouraged' | 'preferred' | 'required';
    requireResidentKey?: boolean;
    userVerification?: 'discouraged' | 'preferred' | 'required';
  };
  attestation?: 'none' | 'indirect' | 'direct' | 'enterprise';
}

/** §12.4 approve body. */
export interface ApproveBody {
  plan_sha256?: string;
  webauthn?: WebAuthnAssertion;
}

/** §12.6 `GET /v1/me`. */
export interface Me {
  principal: { id: string; kind: PrincipalKind; role: PrincipalRole; display_name?: string };
  token: { id: string; scopes: string[]; expires_at: string | null } | null;
  session: { id: string; expires_at: string } | null;
  passkeys: number;
  capabilities: string[];
}

/** §12.6 login answer for apps and the CLI (bearer, not cookie). */
export interface LoginResult {
  access_token: string;
  expires_at: string;
  refresh_token?: string;
}

/** §12.14 severities and inbox item. */
export type Severity = 'info' | 'warning' | 'critical';

export interface InboxItem {
  id: string;
  severity: Severity;
  topic: string;
  title: string;
  body: string;
  link: string | null;
  source: string;
  action_id?: string | null;
  alert_id?: string | null;
  created_at: string;
  read_at: string | null;
}

/** §12.14 alert record (`onemind.alert/v1`). */
export interface AlertRecord {
  id: string;
  type: string;
  severity: Severity;
  title: string;
  body: string;
  subject?: Record<string, string>;
  source_id?: string;
  state: 'open' | 'acknowledged' | 'resolved';
  dedupe_key?: string;
  opened_at: string;
  updated_at?: string;
  resolved_at?: string | null;
  occurrences?: number;
  flapping?: boolean;
  fix: { type: string; params: Record<string, unknown> } | null;
  learn_more_url?: string | null;
}

/** §12.14 push registration. `environment` and `bundle_id` are mobile proposals for the APNs relay (mobile/docs/push.md). */
export interface PushRegistrationRequest {
  platform: 'webpush' | 'unifiedpush' | 'apns';
  endpoint?: string;
  token?: string;
  keys?: { p256dh: string; auth: string };
  label: string;
  environment?: 'sandbox' | 'production';
  bundle_id?: string;
}

export interface PushRegistration extends PushRegistrationRequest {
  id: string;
  created_at?: string;
}

/**
 * Device registry (docs/umbrel2/clients.md §4.4, CLIENT-2; not yet in the contract).
 * A device request files the owner-approved action `device.add`.
 */
export interface DeviceRequestBody {
  name: string;
  kind: 'phone';
  platform: 'ios' | 'android';
  app_version: string;
  os_version: string;
  jwk: EcPublicJwk;
}

export interface EcPublicJwk {
  kty: 'EC';
  crv: 'P-256';
  x: string;
  y: string;
}

export type DeviceState = 'pending' | 'active' | 'denied' | 'revoked';

export interface DeviceRequest {
  id: string;
  state: DeviceState;
  device_id?: string;
  action_id?: string | null;
  /** One-time code the requester polls with (clients.md §4.4). */
  poll_code?: string;
  /** Present once, when the request turns `active`. */
  one_time?: { refresh_token?: string };
}

/** §12.8 event envelope `onemind.event/v1`. */
export interface HubEvent {
  schema: 'onemind.event/v1';
  id: string;
  type: string;
  ts: string;
  subject?: Record<string, string>;
  severity?: Severity;
  data?: Record<string, unknown>;
}

/** §3 error codes plus the §12.2 additions. */
export type ApiErrorCode =
  | 'permission_denied'
  | 'stale_precondition'
  | 'expired'
  | 'conflict'
  | 'outcome_unknown'
  | 'not_found'
  | 'unauthenticated'
  | 'rate_limited'
  | 'unavailable'
  | 'payload_too_large'
  | 'policy_refused';

/** §3 envelope with the optional §12.2 fields. Clients branch on `error` (and `reason`) only. */
export interface ApiErrorBody {
  error: string;
  message: string;
  reason?: string;
  request_id?: string;
  details?: Array<{ field?: string; problem?: string }>;
  retry_after_s?: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | 'network' | 'unknown';
  /** §12.2 open-ended reason (`step_up_required`, `plan_changed`, …). */
  readonly reason?: string;
  readonly retryAfterS?: number;

  constructor(status: number, code: ApiError['code'], message: string, extra: { reason?: string; retryAfterS?: number } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.reason = extra.reason;
    this.retryAfterS = extra.retryAfterS;
  }
}

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

export type ActionType = 'app.install' | 'app.remove';

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

export type PrincipalKind = 'person' | 'agent';
export type PrincipalRole = 'owner' | 'adult' | 'guest' | 'agent';

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
  params: { app_id: string };
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
}

/** §3 error body. */
export type ApiErrorCode =
  | 'permission_denied'
  | 'stale_precondition'
  | 'expired'
  | 'conflict'
  | 'outcome_unknown'
  | 'not_found'
  | 'unauthenticated';

export interface ApiErrorBody {
  error: ApiErrorCode;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | 'network' | 'unknown';

  constructor(status: number, code: ApiError['code'], message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

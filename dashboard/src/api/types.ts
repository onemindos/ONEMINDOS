// SPDX-License-Identifier: Apache-2.0
// Types for the proof-of-concept v0 contract (sdk/contracts/poc-v0.md).
// Section numbers below refer to that file.
import type { components } from '@onemind/sdk';

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
  /** §12.1: features this gateway serves; absent on a v0 gateway. */
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
export type ScanSummary = components['schemas']['ScanSummary'];

/** #724: one strength of what an app needs from a machine (sdk/schema $defs/machineNeeds). A fact the manifest does not state is absent. */
export interface MachineNeedsBlock {
  arch?: string[];
  memoryMb?: number;
  storageFreeGb?: number;
  accelerator?: { capability?: string; minMemoryMb?: number; rtCores?: boolean; count?: number; overlay?: string };
  devices?: string[];
  radios?: string[];
  models?: { quantisations?: string[] };
}

/** §3 `GET /v1/apps` item, built from §4 `onemind.app.yaml`, plus the §11.4 fields. */
export interface CatalogApp {
  id: string;
  /** The gateway sends null when the manifest leaves a field out (core/onemind_core/models.py). */
  name: string | null;
  version: string | null;
  description: string | null;
  category: string | null;
  icon: string | null;
  license: string | null;
  /** #173 metadata.licenceClass: L1 and L2 are green; blocked and unknown are not. Absent on an older gateway. */
  licence_class?: components['schemas']['CatalogApp']['licence_class'];
  source: string | null;
  archs: string[];
  /** spec.requires exactly as written, in either spelling; read machine_needs for one shape. */
  requires: { gpu?: boolean; minMemoryMb?: number };
  /** #724: requires / recommends / supports in one shape, whichever spelling the manifest uses. */
  machine_needs?: { requires: MachineNeedsBlock; recommends: MachineNeedsBlock; supports: MachineNeedsBlock };
  web_port: number | null;
  /** #692: a browser app, opened in a dashboard window with the person's own profile (/browser/<id>). */
  browser?: boolean;
  installed: boolean;
  status: string;
  links: AppLinks;
  tier: AppTier | null;
  /** Last scan, or null when the app has never been scanned (or its record is unreadable). */
  scan: ScanSummary | null;
}

export type ActionType = components['schemas']['PlainActionRequest']['type'] | components['schemas']['ConfigureActionRequest']['type'];
export type AppParams = components['schemas']['PlainActionParams'] & Partial<Pick<components['schemas']['ConfigureActionParams'], 'settings'>> & { name?: undefined };
export type PlanPreview = components['schemas']['PlanPreview'];
/** Body of POST /v1/actions/{id}/approve (§12.4): the plan read, the passkey assertion, the sealed secrets form. */
export type ApproveBody = components['schemas']['onemind_core__routers__actions__ApproveBody'];
/** Validated dashboard view of the SDK's opaque apps.settings response, not a wire contract. */
export interface AppSettings {
  fields: Array<{
    name: string; title?: string; type: string; default?: string | number | boolean; enum?: Array<string | number | boolean>; description?: string; restart?: boolean;
    minimum?: number; maximum?: number; minLength?: number; maxLength?: number; pattern?: string;
  }>;
  values: Record<string, string | number | boolean> | null;
}

/** Validated view of GET /v1/apps/{id}/dependencies (contract §12.22, PD-10). */
export interface AppDependencies {
  app_id: string;
  requires: Array<{
    id: string; alternatives: string[]; reason: string | null; port: number | null; satisfied_by: string | null;
    choices: Array<{ id: string; name: string | null; in_catalog: boolean; installed: boolean }>;
  }>;
  dependents: Array<{ id: string; name: string | null }>;
}

/** Validated view of GET /v1/apps/{id}/host-ports (PD-11). `with` names who already holds the port. */
export interface AppHostPorts {
  app_id: string;
  node_id: string;
  declared: Array<{ port: number; protocol: string; description: string | null }>;
  conflicts: Array<{ port: number; protocol: string; with: string }>;
}

/** Validated view of one GET /v1/sources row (PD-12): a community source pinned at a commit. */
export interface CommunitySource {
  id: string; name: string; url: string; commit: string; state: string; added_at: string | null;
  apps: Array<{ id: string; version: string; scan: { result: string; scanned_at: string | null } | null }>;
  errors: string[];
}

/** PLG-GIT-01: the custom-app shapes come from the generated client, not hand-written types. */
export type CustomPlan = components['schemas']['CustomPlanResult'];
export type CustomRevision = components['schemas']['CustomRevisionOut'];
export type CustomApp = components['schemas']['CustomAppRow'];
export type CustomRollbackPlan = components['schemas']['CustomRollbackResult'];

/** POST /v1/deploy/compose (PD-13): a conversion only; it writes nothing on the box. */
export interface ComposeResult {
  ok: boolean;
  app_id: string;
  files: Record<string, string>;
  refusals: Array<{ service: string | null; rule: string; field: string; message: string }>;
  warnings: string[];
}

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
export type PrincipalRole = 'owner' | 'adult' | 'guest' | 'child' | 'teen' | 'agent';

/** §3 tokens map to principals `{id, kind, role}`. */
export interface Principal {
  id: string;
  kind: PrincipalKind;
  role: PrincipalRole;
}

/** MACH-01 (#281): machine requests. They carry a machine `name`, never an `app_id`. */
export type MachineActionType = Extract<components['schemas']['FeatureActionRequest']['type'], `machine.${string}`> | 'machines.enable' | 'machines.disable';
export type MachineMedia = Pick<components['schemas']['UploadedMedia'], 'size_bytes' | 'sha256'> & { upload_id: string };
export type MachineSource = ({ kind: 'catalogue' } & Pick<components['schemas']['CatalogueImage'], 'url' | 'sha256'>)
  | ({ kind: 'iso' | 'disk' } & MachineMedia);
export interface MachineParams {
  /** Absent on machines.enable and machines.disable, which are about the whole extension. */
  name?: string;
  ram_mb?: number;
  cpus?: number;
  disk_gb?: number;
  image_url?: string;
  /** Delete only: the machine's name typed again by the owner. */
  confirm?: string;
  /** Snapshot only: the snapshot's name. Clone only: `source` is the machine to copy and `name` the new one. */
  snapshot?: string;
  source?: string | MachineSource;
  firmware?: 'bios' | 'uefi';
  tpm?: boolean;
  virtio_drivers?: MachineMedia;
  network?: 'isolated' | 'machine_peers';
  app_id?: undefined;
  settings?: undefined;
}
export type MachineState = 'creating' | 'stopped' | 'running' | 'unknown';
/** GET /v1/machines rows (core/onemind_core/machines/store.py; the OpenAPI response is untyped). */
export interface MachineRecord {
  name: string;
  node_id: string;
  ram_mb: number;
  cpus: number;
  disk_gb: number;
  state: MachineState | string;
  created_at: string;
  updated_at: string;
}
/** GET /v1/machines/{name}/snapshots rows. `consistency` says how safe the copy is; `note` says it in words. */
export interface MachineSnapshot {
  machine: string;
  name: string;
  consistency: 'offline' | 'quiesced' | 'best_effort' | 'quiesce_failed' | string;
  note: string;
  created_at: string;
}
/** GET /v1/machines/capabilities, the parts the screen shows. */
export interface MachineCapabilities {
  image_catalogue?: components['schemas']['MachineCapabilities']['image_catalogue'];
  enabled: boolean;
  extension: { state: string; message: string };
  requirements: { min_memory_mb: number; arch: string; kvm: boolean };
  eligible_node_ids: string[];
  nodes: Array<{ node_id: string; eligible: boolean; reasons: Array<{ code: string; message: string }> }>;
}

/** §3 `POST /v1/actions` body. */
export interface ActionRequest {
  type: ActionType | MachineActionType;
  params: AppParams | MachineParams;
  plan_sha256?: string;
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
  approval?: components['schemas']['Action']['approval'];
  /** D-028: the key level approving needs now (awaiting_approval, read by a person). */
  required_level?: components['schemas']['Action']['required_level'];
  plan?: PlanPreview['plan'] | null;
  progress?: { step: string; pct: number } | null;
  id: string;
  state: ActionState;
  requested_by?: Principal;
  created_at?: string;
  updated_at?: string;
  decided_by?: Principal | null;
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
  | 'unauthenticated'
  | 'rate_limited'
  | 'payload_too_large'
  | 'policy_refused'
  /** The hub no longer serves this dashboard's protocol generation (sdk/contracts/protocol-versions.md). */
  | 'upgrade_required';

export interface ApiErrorBody {
  error: ApiErrorCode;
  message: string;
  /** Machine-readable detail, e.g. step_up_required (sign in again with your passkey). */
  reason?: string | null;
  retry_after_s?: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | 'network' | 'unknown';
  readonly reason: string | undefined;

  constructor(status: number, code: ApiError['code'], message: string, reason?: string | null) {
    super(message);
    this.reason = reason ?? undefined;
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

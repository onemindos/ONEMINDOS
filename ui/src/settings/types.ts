// SPDX-License-Identifier: Apache-2.0
// Data shapes for Settings, Activity and Approvals. Each mirrors a gateway response:
// contract shapes come from sdk/contracts/poc-v0.md §3 (principals, actions, errors, audit);
// the rest are PROPOSED in docs/leap/core/{SECURITY,FABRIC,BACKUPS,UPDATES,DASHBOARD}.md and
// docs/design/TAXONOMY.md. Components render these; they never fetch.
import type { CategorySlug, DeployClass, NodeRole } from './taxonomy';

/* ---------- async state: every panel is one of these ---------- */

/** Contract §3 error body, plus `unavailable` when the hub cannot be reached at all. */
export interface GatewayError {
  error: 'permission_denied' | 'stale_precondition' | 'expired' | 'conflict' | 'outcome_unknown' | 'not_found' | 'unauthenticated' | 'unavailable';
  message: string;
}

/**
 * What the screen knows about one response. `stale: true` means the hub stopped answering and
 * `data` is the last known copy from `asOf` (PRINCIPLES P2: never shown as live).
 */
export type Loadable<T> =
  | { status: 'loading' }
  | { status: 'error'; error: GatewayError }
  | { status: 'ready'; data: T; asOf: string; stale?: boolean };

/** Contract §3 principal, with the proposed `device` and `system:*` families. */
export interface Principal {
  id: string;
  kind: 'person' | 'agent' | 'device' | 'system';
  role?: 'owner' | 'adult' | 'guest' | 'agent';
}

/** What a settings control asks for. `instant` only for changes that reduce power (SECURITY §3.4). */
export interface SettingsIntent {
  type: string;
  params: Record<string, unknown>;
  mode: 'request' | 'instant';
  /** Plain words for the toast and the approval card. */
  title: string;
  /** The same call without the UI (P4). */
  call: string;
}
export type OnIntent = (intent: SettingsIntent) => void;

/* ---------- Account & security (SECURITY §3.2–3.3) ---------- */
export interface Session {
  id: string;
  device: string;
  client: 'browser' | 'phone' | 'cli';
  created_at: string;
  last_seen_at: string;
  current?: boolean;
  /** How this session approves: a fresh passkey assertion or the legacy bearer token. */
  approval: 'passkey' | 'token';
}
export type TokenKind = 'pat' | 'agt' | 'plg' | 'nod' | 'aut';
export interface ApiToken {
  id: string;
  name: string;
  principal: string;
  kind: TokenKind;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}
export interface Passkey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}
export interface AccountData {
  person: { id: string; name: string; role: 'owner' | 'adult' | 'guest' };
  /** False until CORE-SEC-2 ships: the passkey list is a placeholder. */
  passkeysAvailable: boolean;
  passkeys: Passkey[];
  totp: boolean;
  requirePasskeyApproval: boolean;
  sessions: Session[];
  tokens: ApiToken[];
}

/* ---------- Users & roles ---------- */
export interface Person {
  id: string;
  name: string;
  role: 'owner' | 'adult' | 'guest';
  signIn: 'passkey' | 'totp' | 'invited';
  last_seen_at: string | null;
}

/* ---------- Devices & nodes (FABRIC) ---------- */
export interface FabricNode {
  node_id: string;
  hostname: string;
  role: NodeRole;
  arch: 'amd64' | 'arm64';
  board: string;
  status: 'online' | 'stale' | 'offline';
  last_seen: string;
  apps: number;
}
export interface JoinCode {
  code: string;
  expires_at: string;
  /** QR modules as rows of 0/1, computed by the gateway (the UI never encodes secrets). */
  qr: number[][];
  role: NodeRole;
}
export interface DevicesData {
  nodes: FabricNode[];
  join: JoinCode | null;
}

/* ---------- Network & mesh ---------- */
export interface NetworkData {
  mesh: { state: 'connected' | 'degraded' | 'off'; peers: number; peersOnline: number; transport: string };
  remote: { enabled: boolean; exposed: Array<{ app_id: string; name: string; tier: 'lan' | 'mesh' | 'public' }> };
  lanNames: Array<{ name: string; target: string; kind: 'mdns' | 'dns' }>;
  certificates: Array<{ id: string; name: string; issuer: 'box-ca' | 'acme'; expires_at: string; covers: string }>;
}

/* ---------- Backups (BACKUPS) ---------- */
export interface BackupDestination {
  id: string;
  name: string;
  kind: 'usb' | 'box' | 's3';
  last_success_at: string | null;
  state: 'current' | 'behind' | 'failing';
  used_gb: number;
}
export interface BackupsData {
  destinations: BackupDestination[];
  schedule: { every: 'hourly' | 'daily'; at: string; keep: string };
  lastVerifiedRestore: { at: string; snapshot: string; scope: string; result: 'ok' | 'failed' } | null;
  snapshots: Array<{ id: string; at: string; size_gb: number; verified: 'ok' | 'failed' | 'untested' }>;
  emergencyKit: { saved: boolean; keys: number; of: number };
}

/* ---------- Updates (UPDATES) ---------- */
export interface UpdatesData {
  version: string;
  slot: 'A' | 'B';
  fallback: { slot: 'A' | 'B'; version: string } | null;
  channel: 'stable' | 'security' | 'beta';
  window: { start: string; end: string };
  available: { version: string; channel: string; notes: string[]; cvesFixed: number; size_mb: number } | null;
  history: Array<{ at: string; from: string; to: string; result: 'kept' | 'rolled-back' | 'failed'; check?: string; by: string }>;
  apps: Array<{ app_id: string; name: string; from: string; to: string; category: CategorySlug; deploy_class: DeployClass; notes: string[] }>;
}

/* ---------- Notifications (NOTIFICATIONS) ---------- */
export type Severity = 'info' | 'warning' | 'critical';
export interface NotifyChannel {
  id: string;
  kind: 'in-app' | 'push-android' | 'push-ios' | 'email' | 'matrix' | 'telegram';
  label: string;
  state: 'ok' | 'failing' | 'off';
  last_delivery_at: string | null;
  minSeverity: Severity;
}
export interface NotificationsData {
  channels: NotifyChannel[];
  quiet: { enabled: boolean; start: string; end: string; allowCritical: boolean };
}

/* ---------- Automation (AUTOMATION) ---------- */
export interface AutomationRule {
  id: string;
  name: string;
  trigger: { kind: 'schedule' | 'event' | 'webhook'; detail: string };
  creates: string;
  /** `ask` waits in Approvals; `standing` is covered by an owner policy with limits. */
  policy: 'ask' | 'standing';
  last_run_at: string | null;
  next_run_at: string | null;
  state: 'on' | 'paused';
}

/* ---------- Agents & MCP (SECURITY §3.4, contract §11.3) ---------- */
export interface AgentPrincipal {
  id: string;
  name: string;
  state: 'active' | 'suspended';
  tools: Array<{ name: string; kind: 'read' | 'request' }>;
  tokens: number;
  last_active_at: string | null;
  week: { asked: number; approved: number; denied: number };
  pending: number;
}
export interface AgentsData {
  mcp: { enabled: boolean; path: string };
  agents: AgentPrincipal[];
}

/* ---------- Storage ---------- */
export interface Disk {
  id: string;
  node: string;
  label: string;
  kind: 'nvme' | 'ssd' | 'hdd' | 'usb';
  role: 'system' | 'data' | 'backup';
  total_gb: number;
  used_gb: number;
  health: 'ok' | 'warn' | 'failing';
  encrypted: boolean;
}
export interface StorageData {
  disks: Disk[];
  apps: Array<{ app_id: string; name: string; category: CategorySlug; deploy_class: DeployClass; used_gb: number }>;
}

/* ---------- About & diagnostics ---------- */
export interface AboutData {
  box: string;
  version: string;
  build: string;
  base: string;
  uptime_s: number;
  components: Array<{ name: string; version: string; state: 'ok' | 'warn' | 'bad' }>;
  lastBundle_at: string | null;
}

/* ---------- Activity: the audit chain (contract §3 audit, SECURITY §3.7) ---------- */
export interface AuditEntry {
  seq: number;
  at: string;
  actor: Principal;
  kind: 'request' | 'decision' | 'result' | 'sign-in' | 'config' | 'checkpoint';
  text: string;
  node?: string;
  app?: string;
  result?: 'ok' | 'warn' | 'bad' | 'info';
  resultLabel?: string;
  /** First characters of this entry's hash; the full hash is in the API. Empty when not chained. */
  hash: string;
}
export interface AuditVerify {
  state: 'verified' | 'broken' | 'checking';
  first: number;
  last: number;
  checked_at: string;
  /** First entry whose hash does not match, when broken. */
  broken_at?: number;
  checkpoint?: { seq: number; at: string; storedOff: string };
}
export interface ActivityData {
  /** Absent when the entries are not from the audit log (see AuditTimeline `chainNote`). */
  verify?: AuditVerify;
  entries: AuditEntry[];
}

/* ---------- Approvals: the gateway-computed plan (DASHBOARD §3.2, APP-B3) ---------- */
export type EffectKind =
  | 'image'
  | 'volume'
  | 'port'
  | 'egress'
  | 'device'
  | 'host-network'
  | 'secret'
  | 'agent-scope'
  | 'restart'
  | 'data-delete'
  | 'exposure';
export interface Effect {
  kind: EffectKind;
  label: string;
  detail?: string;
  risk: 'low' | 'medium' | 'high';
}
export interface ActionPlan {
  action_id: string;
  /** Approving signs this exact hash (SECURITY §3.2). */
  plan_hash: string;
  computed_at: string;
  app?: { id: string; name: string; category: CategorySlug; deploy_class: DeployClass; plugin: boolean };
  placement?: { node: string; fits: boolean; reason: string; stale?: boolean };
  effects: Effect[];
  scan?: { at: string; critical: number; high: number; malware: 'clean' | 'found' };
  undo: 'reversible' | 'snapshot' | 'one-way';
}

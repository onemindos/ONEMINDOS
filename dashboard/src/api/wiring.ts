// SPDX-License-Identifier: Apache-2.0
// The routes added after contract v0 (sdk/openapi/onemind-v1.json, contract §12): sign-in and
// sessions, people, API tokens, notifications, monitoring and the audit chain. Shapes mirror what
// the gateway returns (core/onemind_core/routers/*); the OpenAPI file only names the request bodies.
// Every method is one route. The dashboard calls nothing else.
import type { Action } from './types';

export type PersonRole = 'owner' | 'adult' | 'guest';

export interface PrincipalInfo {
  id: string;
  kind: string;
  role?: string | null;
  display_name?: string;
  username?: string;
}

/** POST /v1/auth/login and /v1/auth/setup (client "app": a bearer access token, no cookie). */
export interface LoginResult {
  access_token: string;
  expires_at: string;
  principal: PrincipalInfo;
  session: { id: string; expires_at: string };
}

export interface Me {
  principal: PrincipalInfo;
  token: { id: string; scopes: string[]; expires_at: string | null; source: string } | null;
  session: { id: string; expires_at: string; auth_method: string; passkey_at: string | null } | null;
  passkeys: number;
  scopes: string[];
  capabilities: string[];
  step_up: { passkeys_active: boolean; require_passkey_approval: boolean };
}

export interface SessionInfo {
  id: string;
  principal_id: string;
  client: string;
  transport: string;
  auth_method: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export interface PasskeyInfo {
  credential_id: string;
  label: string | null;
  created_at: string;
  last_used_at: string | null;
}

/** WebAuthn options as the gateway sends them (base64url strings, JSON). */
export interface WebAuthnOptions {
  challenge_id: string;
  expires_at: string;
  publicKey: Record<string, unknown>;
}

export interface UserInfo {
  id: string;
  username: string | null;
  display_name: string;
  role: PersonRole;
  created_at: string;
  last_seen_at: string | null;
  disabled: boolean;
  enrolled: boolean;
  passkeys: number;
  totp: boolean;
}
export interface UserCreated extends UserInfo {
  one_time: { enrolment_code: string; enrolment_url: string; expires_at: string };
}

export interface TokenInfo {
  id: string;
  prefix: string | null;
  name: string;
  principal_id: string;
  kind: string;
  scopes: string[];
  created_at: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  source: string;
  owner_user_id: string | null;
}
export interface TokenCreated extends TokenInfo {
  /** Shown once. The dashboard keeps it in component state only, never in storage. */
  one_time: { token: string };
}

export type Severity = 'info' | 'warning' | 'critical';

export interface NotificationItem {
  id: string;
  severity: Severity;
  topic: string;
  title: string;
  body: string;
  link: string | null;
  source: string | null;
  action_id: string | null;
  alert_id: string | null;
  created_at: string;
  read_at: string | null;
}

export interface ChannelInfo {
  id: string;
  kind: string;
  label: string;
  content_level: 'opaque' | 'title' | 'full' | null;
  config: Record<string, unknown>;
  verified: boolean;
  state: string;
  last_error: string | null;
  owner_person_id: string | null;
  secret: 'provided' | null;
  created_at: string;
  updated_at: string;
}
export interface ChannelInput {
  kind: string;
  label: string;
  config: Record<string, unknown>;
  content_level?: 'opaque' | 'title' | 'full' | null;
  secret?: string | null;
}

export interface AlertFix {
  type: string;
  params: Record<string, unknown>;
  label?: string;
}
export interface AlertInfo {
  schema: 'onemind.alert/v1';
  id: string;
  type: string;
  severity: Severity;
  title: string;
  body: string;
  subject: Record<string, unknown>;
  state: 'open' | 'acknowledged' | 'resolved';
  occurrences: number;
  flapping: boolean;
  opened_at: string;
  updated_at: string;
  resolved_at: string | null;
  fix: AlertFix | null;
  learn_more_url: string | null;
  topic: string | null;
  link: string | null;
  acked_by: string | null;
  acked_at: string | null;
}

export interface MonitoringSummary {
  nodes: { online: number; stale: number; offline: number };
  apps: Record<string, number>;
  open_alerts: Record<Severity, number>;
  storage: Array<{ node_id: string; state: string | null }>;
  at: string;
}

export interface AuditRecord {
  seq: number;
  ts: string;
  event: string;
  principal: { id: string; kind: string; role?: string | null } | null;
  action_id: string | null;
  data: Record<string, unknown>;
  hash: string;
  prev_hash: string;
}
export interface AuditVerifyResult {
  ok: boolean;
  records: number;
  first_bad_seq: number | null;
  head: { seq: number; hash: string } | null;
  checked_at: string;
  reason: string;
}

export interface WiringApi {
  // sign-in (no credentials needed)
  loginOptions(): Promise<WebAuthnOptions>;
  loginPassword(body: { username: string; password: string; totp?: string }): Promise<LoginResult>;
  loginPasskey(credential: Record<string, unknown>): Promise<LoginResult>;
  /** First owner: `setupToken` is the install owner token or first-boot token, sent as the bearer. */
  setup(setupToken: string, body: { username: string; display_name: string; password: string }): Promise<LoginResult>;
  enrol(body: { code: string; username?: string; password: string }): Promise<LoginResult>;
  // the signed-in person
  me(): Promise<Me>;
  logout(): Promise<void>;
  sessions(): Promise<SessionInfo[]>;
  revokeSession(id: string): Promise<void>;
  passkeys(): Promise<PasskeyInfo[]>;
  passkeyRegisterOptions(): Promise<WebAuthnOptions>;
  passkeyRegister(credential: Record<string, unknown>, label?: string): Promise<PasskeyInfo>;
  deletePasskey(id: string): Promise<void>;
  // people and tokens
  users(): Promise<UserInfo[]>;
  createUser(body: { display_name: string; role: PersonRole; username?: string }): Promise<UserCreated>;
  updateUser(id: string, body: { display_name?: string; role?: PersonRole }): Promise<UserInfo>;
  disableUser(id: string): Promise<UserInfo>;
  tokens(): Promise<TokenInfo[]>;
  createToken(body: { name: string; principal?: 'self' | { kind: 'agent'; id: string }; expires_in_days?: number }): Promise<TokenCreated>;
  rotateToken(id: string, graceS?: number): Promise<TokenCreated>;
  revokeToken(id: string): Promise<void>;
  // notifications
  notifications(opts?: { unread?: boolean; limit?: number }): Promise<NotificationItem[]>;
  markRead(id: string): Promise<NotificationItem>;
  markAllRead(): Promise<{ marked: number }>;
  channels(): Promise<ChannelInfo[]>;
  createChannel(body: ChannelInput): Promise<ChannelInfo>;
  deleteChannel(id: string): Promise<void>;
  testChannel(id: string): Promise<{ ok?: boolean; error?: string | null }>;
  // monitoring
  monitoring(): Promise<MonitoringSummary>;
  alerts(state?: string): Promise<AlertInfo[]>;
  ackAlert(id: string): Promise<AlertInfo>;
  resolveAlert(id: string): Promise<AlertInfo>;
  /** Always `approve: false`: the fix becomes a request in Approvals. This client never approves in the same call. */
  askToFix(id: string, reason?: string): Promise<Action>;
  // audit
  /** Oldest first from `after_seq` (exclusive); callers wanting the newest page pass head.seq - limit. */
  auditEvents(opts?: { limit?: number; after_seq?: number }): Promise<AuditRecord[]>;
  auditVerify(): Promise<AuditVerifyResult>;
}

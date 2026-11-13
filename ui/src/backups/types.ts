// SPDX-License-Identifier: Apache-2.0
// Shapes of contract §12.12 (sdk/contracts/poc-v0.md), as the gateway serves them
// (core/onemind_core/backups/README.md). Components take these and never fetch.

export type BadgeState = 'verified' | 'unverified' | 'stale' | 'failing' | 'none';

export interface BackupBadge {
  state: BadgeState;
  verified_at?: string | null;
  last_success_at?: string | null;
  reason?: string;
}

export type DestinationKind = 'usb' | 'box' | 'rest' | 's3';

export interface Destination {
  id: string;
  kind: DestinationKind;
  label: string;
  primary: boolean;
  append_only: boolean;
  /** Never credentials: usb_uuid, or url and user, or endpoint and bucket. */
  config: Record<string, string | boolean>;
  created_at: string;
}

export type KitStateName = 'missing' | 'issued' | 'confirmed';

export interface KitState {
  state: KitStateName;
  issued_at: string | null;
  confirmed_at: string | null;
  fingerprint: string | null;
  /** 1-based positions of the two groups the owner must type back. */
  positions: number[];
}

/** The one-time part of POST /v1/backups/kit. Shown once; never stored by the UI. */
export interface KitOneTime {
  owner_key: string;
  groups: string[];
  check: string;
  text: string;
  qr_payload: string;
}

export interface BackupsStatus {
  health: 'ok' | 'stale' | 'failing' | 'not_configured';
  reason: string | null;
  last_success_at: string | null;
  last_verified_restore_at: string | null;
  next_run_at: string | null;
  copies: number;
  badges: { box: BackupBadge; system: BackupBadge; apps: Record<string, BackupBadge> };
  destinations: Destination[];
  kit: KitState;
  crash_consistent_apps: string[];
  setup: { blocking: string[] };
  agent: 'ok' | 'off' | 'unreachable';
}

export type RunState = 'running' | 'succeeded' | 'partial' | 'failed' | 'refused';

export interface RunUnit {
  unit: string;
  state: string;
  snapshot_id?: string;
  error?: string;
}

export interface BackupRun {
  id: string;
  action_id: string | null;
  reason: string;
  destination_id: string | null;
  state: RunState;
  started_at: string;
  finished_at: string | null;
  bytes_done: number | null;
  units: RunUnit[];
  error: string | null;
}

export interface Snapshot {
  id: string;
  short_id: string;
  unit: string;
  app_id: string | null;
  taken_at: string;
  reason: string;
  run_id: string | null;
  paths: string[];
  verified_at: string | null;
}

export interface TreeEntry {
  name: string;
  path: string;
  type: 'file' | 'dir' | 'symlink' | 'other';
  size: number;
  mtime?: string;
}

export interface RestorePlan {
  summary: string;
  app_id: string;
  snapshot: { id: string; taken_at: string; reason: string };
  database: boolean;
  steps: string[];
  downtime: string;
  warnings: string[];
}

export type RestoreState =
  | 'awaiting_approval' | 'running' | 'succeeded' | 'failed' | 'outcome_unknown' | 'cancelled' | 'expired';

export interface Restore {
  id: string;
  action_id: string;
  snapshot_id: string;
  scope: { app_id: string; path?: string };
  state: RestoreState;
  plan: RestorePlan;
  pre_restore_snapshot_id: string | null;
  health_gate: { verdict: 'pass' | 'fail' | 'error'; [k: string]: unknown } | null;
  steps: { at: string; step: string }[];
  created_at: string;
  finished_at: string | null;
  error: string | null;
}

/** What a screen knows about one remote value. */
export type Load<T> =
  | { status: 'loading' }
  | { status: 'error'; code: string; message: string }
  | { status: 'ready'; data: T; asOf: string; stale?: boolean };

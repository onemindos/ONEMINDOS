// SPDX-License-Identifier: Apache-2.0
// Data shapes for the App Store and the installed-apps manager.
// Contract fields (sdk/contracts/poc-v0.md §3, §4, §9.3, §11.4) keep their wire names.
// Fields marked PROPOSED come from docs/design/TAXONOMY.md §2, §3, §5 and the parity audit
// (PD-01 to PD-09); the gateway does not serve them yet. Components never fetch: callers pass
// these objects in, so the dashboard can hand API responses straight through.
import type { AppTier, ScanSummary } from '../lib/trust';

/** The 16 Market categories (TAXONOMY §1). PROPOSED enum for `metadata.category`. */
export type CategorySlug =
  | 'home'
  | 'files'
  | 'media'
  | 'notes'
  | 'productivity'
  | 'communication'
  | 'ai'
  | 'automation'
  | 'network'
  | 'monitoring'
  | 'news'
  | 'developer'
  | 'family'
  | 'finance'
  | 'learning'
  | 'field';

/** How an app gets onto the box and how far OneMind vouches for it (TAXONOMY §2). Derived by the gateway. */
export type DeployClass = 'core' | 'market-verified' | 'market-community' | 'list-only' | 'private';

/** Licence class (contract §11.1 plus TAXONOMY §2): L1 permissive, L2 copyleft, L3 source-available, L? unclear. */
export type LicenceClass = 'L1' | 'L2' | 'L3' | 'L?';

export type Arch = 'amd64' | 'arm64';
export type NodeRole = 'hub' | 'worker' | 'leaf' | 'any';
export type DeviceClass = 'usb-serial' | 'zigbee' | 'zwave' | 'thread' | 'bluetooth' | 'sdr' | 'lora' | 'camera' | 'coral' | 'gpio';
export type Exposure = 'lan' | 'mesh' | 'public';

/** PROPOSED `spec.placement` (TAXONOMY §5). Every key optional. */
export interface PlacementSpec {
  roles?: NodeRole[];
  gpu?: 'optional' | 'required';
  devices?: { class: DeviceClass; required?: boolean }[];
  hostNetwork?: boolean;
  exposure?: Exposure;
}

/** One release note entry (PROPOSED `releaseNotes`, PD-01). */
export interface ReleaseNote {
  version: string;
  released_at: string;
  /** Plain-language lines, newest first. */
  notes: string[];
  /** Upstream changelog link; only http(s) links are rendered. */
  url?: string;
}

/** A screenshot slot (PROPOSED `gallery`, PU-11). `src` is optional: without it the UI shows a labelled placeholder. */
export interface Screenshot {
  src?: string;
  alt: string;
}

/** The catalog fit summary for one app (PROPOSED `fits` on `GET /v1/apps`). The hub decides; the UI renders. */
export interface FitSummary {
  verdict: 'fits' | 'stale' | 'none';
  /** The node the box would choose. */
  node?: string;
  /** The first reason it does not fit, or why the chosen node is in doubt. */
  reason?: string;
}

/** One `GET /v1/apps` entry: contract fields plus the PROPOSED taxonomy fields. */
export interface CatalogApp {
  // contract §3 / §4
  id: string;
  name: string;
  version: string;
  description: string;
  category: CategorySlug;
  icon?: string | null;
  license: string;
  source?: string;
  archs: Arch[];
  requires?: { gpu?: boolean; minMemoryMb?: number };
  web_port?: number | null;
  installed: boolean;
  // contract §9.3 / §11.4
  links?: { docs?: string | null; github?: string | null; website?: string | null; support?: string | null };
  tier: AppTier | null;
  scan: (ScanSummary & { smoke?: 'pass' | 'fail' | 'skipped' }) | null;
  upstream?: { release: string; released_at: string; archived: boolean };
  updates?: { channel: 'security' | 'stable'; automerge: 'patch' | 'none' };
  // PROPOSED (TAXONOMY §2, §3, §5; PD-01)
  tags?: string[];
  deploy_class: DeployClass;
  plugin?: boolean;
  licence_class?: LicenceClass;
  tagline?: string;
  placement?: PlacementSpec;
  storage?: { data?: { size: string; backup: boolean } };
  permissions?: string[];
  /** What a plugin adds to OneMind (widgets, settings, tools, an agent principal). */
  extensions?: string[];
  /** Market community: the checks it did not pass. */
  community_gaps?: string[];
  /** List-only: why OneMind cannot ship it. */
  list_only_reason?: string;
  release_notes?: ReleaseNote[];
  gallery?: Screenshot[];
  fit?: FitSummary;
  /** Newest scan or listing date, for "Verified this week". */
  listed_at?: string;
}

/** PROPOSED `GET /v1/apps/{id}/plan` (PD-04, TAXONOMY §3.3). */
export interface NodeFit {
  node: string;
  fits: boolean;
  /** Plain-language reasons: what matched, or the first failing facet. */
  reasons: string[];
  /** The node's last report is older than 30 s: never treated as live (PRINCIPLES P2). */
  stale?: boolean;
  last_seen?: string;
  chosen?: boolean;
  /** Free memory on the node, for the requirement meter. */
  mem_free_mb?: number;
  mem_total_mb?: number;
}

export interface AppPlan {
  app_id: string;
  nodes: NodeFit[];
  dependencies?: string[];
  volumes?: { name: string; size: string; backup: boolean }[];
  host_ports?: number[];
  /** Scopes an agent principal gets if the app carries one (contract §11.2). */
  agent_scopes?: string[];
}

/** Lifecycle state of an installed app (contract `status`, plus PROPOSED values). */
/** `installed`: the gateway applied it but reports no health yet (contract v0 `status: installed`). */
export type InstalledRunState = 'running' | 'installed' | 'starting' | 'stopped' | 'unhealthy' | 'updating' | 'unknown';

/** PROPOSED: a credential from the manifest (PD-07). Sealed on the box; shown only to the owner. */
export interface AppCredential {
  label: string;
  value: string;
  /** Hidden until revealed. */
  secret?: boolean;
}

export interface HistoryEntry {
  at: string;
  text: string;
  by: string;
  result: 'succeeded' | 'failed' | 'rolled_back' | 'cancelled';
}

/** A settings field from the app's PROPOSED settings schema (PD-09). Saved as one `app.configure` request. */
export interface SettingField {
  key: string;
  label: string;
  kind: 'text' | 'number' | 'boolean' | 'select';
  value: string | number | boolean;
  options?: string[];
  hint?: string;
  /** Changing it restarts the app. */
  restarts?: boolean;
}

export interface LogLine {
  at: string;
  level: 'debug' | 'info' | 'warn' | 'error';
  text: string;
}

/** An installed app as the manager shows it. */
export interface InstalledApp {
  app: CatalogApp;
  node: string;
  state: InstalledRunState;
  /** When the hub last heard about this app's health. */
  checked_at: string;
  /** PROPOSED per-app URL behind the gateway login (PD-02). */
  url?: string;
  update?: ReleaseNote;
  data_size?: string;
  last_backup?: string | null;
  credentials?: AppCredential[];
  first_run?: string[];
  settings?: SettingField[];
  history?: HistoryEntry[];
}

/** Contract §3 types plus the PROPOSED lifecycle actions (PD-03, PD-06). */
export type StoreActionType =
  | 'app.install'
  | 'app.remove'
  | 'app.start'
  | 'app.stop'
  | 'app.restart'
  | 'app.update'
  | 'app.configure'
  | 'app.delete_data';

export interface StoreActionRequest {
  type: StoreActionType;
  params: Record<string, unknown> & { app_id: string };
  /** Plain-language line for toasts and the approval card. */
  summary: string;
}

/** Progress of a request from Approvals to a healthy app (PU-06 jobs tray). */
export type JobState =
  | 'awaiting_approval'
  | 'pulling'
  | 'starting'
  | 'healthy'
  | 'rolled_back'
  | 'failed'
  | 'denied'
  | 'expired';

export interface StoreJob {
  action_id: string;
  app_id: string;
  app_name: string;
  type: StoreActionType;
  state: JobState;
  /** 0-100 from the executor (PROPOSED step and %, PD-03); absent means indeterminate. */
  percent?: number;
  message?: string;
  updated_at: string;
  requested_by?: string;
}

/** A Discover row from a repo file (PU-11). */
export interface Collection {
  id: string;
  title: string;
  blurb?: string;
  app_ids: string[];
}

/** Load state every data-bound component accepts (IA §4 screen-states checklist). */
export type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; code: string; message: string }
  | { kind: 'ready'; fetched_at: string; stale?: boolean };

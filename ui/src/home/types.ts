// SPDX-License-Identifier: Apache-2.0
// Data shapes Home renders. Fields named after sdk/contracts/poc-v0.md where the contract
// defines them (§2 heartbeat, §3 nodes/apps/actions); everything marked PROPOSED needs a
// contract amendment and is listed in ui/src/home/README.md.
import type { ActionSummary } from '../components/ApprovalCard';
import type { NodeSummary } from '../components/NodeCard';
import type { Tone } from '../tokens/tokens';
import type { DeployClass } from './taxonomy';

/** Something Home asked the gateway for: still loading, failed (contract error shape), or here. */
export type Loadable<T> =
  | { state: 'loading' }
  | { state: 'error'; error: string; message: string }
  | { state: 'ready'; data: T };

/** Contract §2 heartbeat as served by `GET /v1/nodes` (§3), plus two PROPOSED fields. */
export interface HomeNode
  extends Pick<
    NodeSummary,
    'node_id' | 'hostname' | 'role' | 'arch' | 'cpus' | 'mem_total_mb' | 'mem_available_mb' | 'disk_total_gb' | 'disk_free_gb' | 'last_seen' | 'status'
  > {
  /** contract §2 */
  uptime_s?: number;
  /** PROPOSED heartbeat field: CPU use over the last interval, 0..100. */
  cpu_percent?: number | null;
  /** PROPOSED heartbeat field: hottest CPU/SoC sensor in °C; null when the board has none. */
  temp_c?: number | null;
}

export type AppRunState = 'running' | 'starting' | 'updating' | 'stopped' | 'unhealthy' | 'unknown';

/** Typed widget templates (PLUGIN-UI.md §2). The host renders; no app code runs here. */
export type AppWidgetPayload =
  | { template: 'stat'; value: string | number; unit?: string; label: string; tone?: Tone; updated_at: string }
  | { template: 'stats'; items: Array<{ value: string | number; label: string }>; updated_at: string }
  | { template: 'list'; items: Array<{ text: string; detail?: string; at?: string }>; updated_at: string }
  | { template: 'progress'; label: string; value: number; max: number; text: string; updated_at: string }
  | { template: 'status'; tone: Tone; label: string; detail?: string; updated_at: string };

export type WidgetTemplate = AppWidgetPayload['template'];

/** `spec.ui.widgets[]` in the app manifest (PLUGIN-UI.md §5, PROPOSED). */
export interface AppWidgetDecl {
  id: string;
  title: string;
  template: WidgetTemplate;
  source: { path: string; refreshSeconds: number };
}

/** One catalog entry (contract §3 `GET /v1/apps`) with the TAXONOMY.md fields. */
export interface HomeApp {
  id: string;
  name: string;
  version: string;
  description: string;
  /** contract: free slug today; TAXONOMY.md §5 makes it one of 16. Legacy slugs are mapped. */
  category: string;
  /** TAXONOMY.md §5, PROPOSED: 0-3 sub-tags from the category's list. */
  tags?: string[];
  /** TAXONOMY.md §2, PROPOSED catalog field. Unknown = not reported. */
  deploy_class?: DeployClass;
  /** TAXONOMY.md §2: the app also adds widgets, settings or an agent to OneMind. */
  plugin?: boolean;
  installed: boolean;
  status?: AppRunState;
  /** Node the app runs on (hostname). */
  node?: string;
  /** Where Open goes: the app's own address behind the gateway login (PROPOSED, SEC-P2). */
  open_url?: string;
  /** contract `icon`: an http(s) URL; Home falls back to a generated monogram. */
  icon?: string;
  /** Monogram colour when there is no icon: a status-free hue from the token set. */
  hue?: 'teal' | 'blue' | 'violet' | 'green' | 'amber' | 'red' | 'neutral';
  update_available?: string;
  widgets?: AppWidgetDecl[];
}

export interface ActivityItem {
  seq: number;
  at: string;
  actor: { kind: 'person' | 'agent' | 'system'; name: string };
  text: string;
  result?: { tone: Tone; label: string };
}

/** PROPOSED (backup agent, BAK-B1). */
export interface BackupStatus {
  last_run: string | null;
  last_verified_restore: string | null;
  destinations: Array<{ name: string; last_success: string | null; state: 'ok' | 'behind' | 'failing' }>;
  observed_at: string;
}

/** PROPOSED (updater read endpoint, OSU-P1). */
export interface UpdatesStatus {
  os: { from: string; to: string; channel: 'security' | 'stable'; action_id?: string } | null;
  apps: Array<{ app_id: string; from: string; to: string }>;
  checked_at: string;
}

/** PROPOSED (fabric links, FAB-P1). */
export interface MeshStatus {
  links: Array<{ hostname: string; via: 'lan' | 'mesh' | 'leaf'; state: 'up' | 'degraded' | 'down'; rtt_ms?: number | null }>;
  remote_access: 'off' | 'mesh' | 'public';
  observed_at: string;
}

/** Optional weather slot, fed by an app widget (for example a Home Assistant sensor). */
export interface WeatherSlot {
  temp_c: number;
  summary: string;
  source: string;
  updated_at: string;
}

export interface HomeData {
  /** Freshness of the hub's own answer: Home never shows a cached green (P2). */
  hub: { observed_at: string };
  nodes: Loadable<HomeNode[]>;
  apps: Loadable<HomeApp[]>;
  approvals: Loadable<ActionSummary[]>;
  activity: Loadable<ActivityItem[]>;
  backups: Loadable<BackupStatus>;
  updates: Loadable<UpdatesStatus>;
  mesh: Loadable<MeshStatus>;
  /** App widget payloads keyed `${appId}/${widgetId}`. Missing key = not fetched yet. */
  appWidgets: Record<string, Loadable<AppWidgetPayload>>;
  weather?: WeatherSlot | null;
}

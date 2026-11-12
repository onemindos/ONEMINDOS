// SPDX-License-Identifier: Apache-2.0
// Contract shapes (sdk/contracts/poc-v0.md §2, §3, §11.4) → the props @onemind/ui renders.
// Pure functions, so every mapping is unit-tested without a browser. Nothing here invents data
// the gateway did not send: a field the contract lacks stays undefined and the ui component
// says "unknown" or "not reported".
import {
  CATEGORY_BY_SLUG,
  type ActionSummary,
  type AppRunState,
  type AuditEntry,
  type CategorySlug,
  type DeployClass,
  type HomeApp,
  type HomeNode,
  type InstalledApp,
  type InstalledRunState,
  type JobState,
  type ActivityItem,
  type PaletteApp,
  type ShellNotification,
  type StoreJob,
  type CatalogApp as StoreApp,
} from '@onemind/ui';
import type { Action, ActionState, CatalogApp, NodeRecord, NodeStatus } from '../api/types';

/** Category slugs on `main` that predate TAXONOMY.md §1 (§1.3 maps them). */
const LEGACY_CATEGORY: Record<string, CategorySlug> = {
  'home-automation': 'home',
  iot: 'home',
  notifications: 'automation',
  security: 'network',
  passwords: 'network',
};

/** One of the 16 TAXONOMY slugs, or undefined when the catalog's value cannot be placed. */
export function categorySlug(raw: string | null | undefined): CategorySlug | undefined {
  if (!raw) return undefined;
  if (raw in CATEGORY_BY_SLUG) return raw as CategorySlug;
  return LEGACY_CATEGORY[raw];
}

/**
 * Deployment class (TAXONOMY §2) is not served yet; the §11.4 tier is the closest fact.
 * verified and blocked come through the Market gate; anything else is "not fully checked".
 */
export function deployClass(tier: CatalogApp['tier']): DeployClass {
  return tier === 'verified' || tier === 'blocked' ? 'market-verified' : 'market-community';
}

const ARCHS = new Set(['amd64', 'arm64']);
const nameOf = (a: Pick<CatalogApp, 'id' | 'name'>) => a.name || a.id;

/** Only an absolute http(s) URL or a same-origin path is used as an icon; else the monogram. */
export function iconOf(icon: string | null | undefined): string | undefined {
  if (!icon) return undefined;
  if (icon.startsWith('/') && !icon.startsWith('//')) return icon;
  try {
    const u = new URL(icon);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : undefined;
  } catch {
    return undefined;
  }
}

/** §3 `GET /v1/apps` entry → Market card. `category` keeps an unknown slug, so the card says "Uncategorised". */
export function toStoreApp(a: CatalogApp): StoreApp {
  return {
    id: a.id,
    name: nameOf(a),
    version: a.version ?? 'unknown',
    description: a.description ?? '',
    category: (categorySlug(a.category) ?? a.category ?? 'uncategorised') as CategorySlug,
    icon: iconOf(a.icon) ?? null,
    license: a.license ?? 'unknown',
    source: a.source ?? undefined,
    archs: a.archs.filter((x): x is 'amd64' | 'arm64' => ARCHS.has(x)),
    requires: a.requires,
    web_port: a.web_port,
    installed: a.installed,
    links: a.links,
    tier: a.tier,
    scan: a.scan,
    deploy_class: deployClass(a.tier),
  };
}

/**
 * Where "Open" goes. Contract v0 has no per-app address (§12 adds one behind the gateway login),
 * so it is the app's web port on the host that served this page, as in dashboard v0.
 */
export function openUrl(a: Pick<CatalogApp, 'web_port' | 'installed'>, loc: Pick<Location, 'protocol' | 'hostname'> = window.location): string | undefined {
  if (!a.installed || !a.web_port) return undefined;
  return `${loc.protocol}//${loc.hostname}:${a.web_port}/`;
}

/** Gateway app `status` → run state. `installed` means applied, not "healthy": v0 reports no health. */
export function runState(status: string): AppRunState & InstalledRunState {
  switch (status) {
    case 'installed':
      return 'installed';
    case 'installing':
      return 'starting';
    case 'failed':
      return 'unhealthy';
    default:
      return 'unknown';
  }
}

export function toHomeApp(a: CatalogApp, loc?: Pick<Location, 'protocol' | 'hostname'>): HomeApp {
  return {
    id: a.id,
    name: nameOf(a),
    version: a.version ?? 'unknown',
    description: a.description ?? '',
    category: categorySlug(a.category) ?? a.category ?? '',
    deploy_class: deployClass(a.tier),
    installed: a.installed,
    status: runState(a.status),
    open_url: openUrl(a, loc),
    icon: iconOf(a.icon),
  };
}

/** What `openUrl` is: the app's own port, which no OneMind sign-in guards on a v0 hub. */
export const DIRECT_URL_NOTE = 'the app’s own port on this host, not behind the OneMind sign-in';

/** An installed app for the manager. The hub reports no node or health per app in v0. */
export function toInstalled(a: CatalogApp, checkedAt: string, loc?: Pick<Location, 'protocol' | 'hostname'>): InstalledApp {
  const url = openUrl(a, loc);
  return {
    app: toStoreApp(a),
    node: 'this OneMind (the hub places it)',
    state: runState(a.status),
    checked_at: checkedAt,
    url,
    url_note: url ? DIRECT_URL_NOTE : undefined,
  };
}

export function toHomeNode(n: NodeRecord, status: NodeStatus = n.status): HomeNode {
  return {
    node_id: n.node_id,
    hostname: n.hostname,
    role: n.role,
    arch: n.arch,
    cpus: n.cpus,
    mem_total_mb: n.mem_total_mb,
    mem_available_mb: n.mem_available_mb,
    disk_total_gb: n.disk_total_gb,
    disk_free_gb: n.disk_free_gb,
    last_seen: n.last_seen,
    status,
    uptime_s: n.uptime_s,
  };
}

const RESULT_MESSAGE: ReadonlySet<ActionState> = new Set(['failed', 'outcome_unknown']);

/**
 * §12.1 adds the principal kinds `plugin`, `automation` and `node`; the ui pills know only person
 * and agent. Anything that is not a person is shown as not a person, so an automation or a plugin
 * never reads "Person" on an approval card.
 */
export function requesterKind(kind: string | undefined): 'person' | 'agent' {
  return kind === 'person' ? 'person' : 'agent';
}

export function toActionSummary(a: Action): ActionSummary {
  const rb = a.requested_by;
  const db = a.decided_by;
  return {
    id: a.id,
    type: a.type,
    params: a.params,
    state: a.state,
    expires_at: a.expires_at,
    created_at: a.created_at,
    requested_by: rb ? { id: rb.id, kind: requesterKind(rb.kind), role: rb.role } : undefined,
    decided_by: db ? { id: db.id, kind: db.kind } : undefined,
    message: RESULT_MESSAGE.has(a.state) ? (a.result?.message ?? undefined) : undefined,
  };
}

/** Action state → install progress. The v0 executor reports no steps, only these states. */
export function jobState(s: ActionState): JobState {
  switch (s) {
    case 'requested':
    case 'awaiting_approval':
      return 'awaiting_approval';
    case 'accepted':
      return 'pulling';
    case 'dispatched':
      return 'starting';
    case 'succeeded':
      return 'healthy';
    case 'expired':
      return 'expired';
    case 'cancelled':
      return 'denied';
    default:
      return 'failed';
  }
}

const JOB_MESSAGE: Partial<Record<ActionState, string>> = {
  accepted: 'Approved. The hub is applying it.',
  dispatched: 'The hub is starting it.',
  succeeded: 'Applied. This hub version does not check app health yet.',
  outcome_unknown: 'The hub lost track of this request; check the app before trying again.',
};

export function toJob(a: Action, appName: string): StoreJob {
  return {
    action_id: a.id,
    app_id: appIdOf(a) ?? '',
    app_name: appName,
    type: a.type,
    state: jobState(a.state),
    message: a.result?.message && RESULT_MESSAGE.has(a.state) ? a.result.message : JOB_MESSAGE[a.state],
    updated_at: a.updated_at ?? a.created_at ?? a.expires_at,
    requested_by: a.requested_by?.id,
  };
}

export const TERMINAL: ReadonlySet<ActionState> = new Set(['succeeded', 'failed', 'outcome_unknown', 'expired', 'cancelled']);
export const isActive = (a: Pick<Action, 'state'>) => !TERMINAL.has(a.state);

const VERB: Partial<Record<string, string>> = { 'app.install': 'Install', 'app.remove': 'Remove' };
const timeOf = (a: Action) => a.updated_at ?? a.created_at ?? a.expires_at;

/**
 * The app an action is about, if any. §12.5 adds types (additive, §12.1) whose params carry a
 * node_id or nothing, so neither `params.app_id` nor the type is assumed.
 */
export function appIdOf(a: Pick<Action, 'params'>): string | undefined {
  const id = (a.params as Record<string, unknown> | undefined)?.app_id;
  return typeof id === 'string' ? id : undefined;
}

/** "Install Ollama" for the §3 types; any other type is named as the hub sent it. */
function describe(a: Action, names: (id: string) => string): { verb: string; subject: string; what: string } {
  const appId = appIdOf(a);
  const nodeId = (a.params as Record<string, unknown> | undefined)?.node_id;
  const subject = appId ? names(appId) : typeof nodeId === 'string' ? nodeId : '';
  const verb = VERB[a.type] ?? a.type;
  return { verb, subject, what: `${verb} ${subject}`.trim() };
}

/**
 * The notification centre until the notifications API lands (§12, CORE-NOTIFY): built from
 * actions and node status. Ids are stable per fact, so "read" survives a reload.
 */
export function notificationsFrom(actions: Action[], nodes: Array<Pick<NodeRecord, 'node_id' | 'hostname' | 'last_seen'> & { status: NodeStatus }>, names: (id: string) => string, read: ReadonlySet<string>): ShellNotification[] {
  const out: ShellNotification[] = [];
  for (const a of actions) {
    const { subject: app, what } = describe(a, names);
    const appId = appIdOf(a);
    const base = { source: 'approvals', created: timeOf(a), actionId: a.id };
    let n: Omit<ShellNotification, 'read'> | undefined;
    if (a.state === 'awaiting_approval')
      n = { ...base, id: `act:${a.id}:waiting`, kind: 'approval_waiting', severity: 'warning', title: `${what} is waiting for approval`, body: a.requested_by ? `Asked by ${a.requested_by.id}.` : undefined, href: `/approvals?highlight=${encodeURIComponent(a.id)}` };
    else if (a.state === 'succeeded')
      n = { ...base, id: `act:${a.id}:done`, kind: a.type === 'app.install' ? 'app_installed' : 'info', severity: 'info', title: a.type === 'app.install' ? `${app} installed` : a.type === 'app.remove' ? `${app} removed` : `${what}: done`, href: a.type === 'app.install' && appId ? `/installed/${encodeURIComponent(appId)}` : '/activity' };
    else if (a.state === 'failed' || a.state === 'outcome_unknown')
      n = { ...base, id: `act:${a.id}:failed`, kind: 'info', severity: 'critical', title: `${what} ${a.state === 'failed' ? 'failed' : 'has an unknown outcome'}`, body: a.result?.message ?? undefined, href: '/activity' };
    else if (a.state === 'expired')
      n = { ...base, id: `act:${a.id}:expired`, kind: 'info', severity: 'info', title: `${what} expired without a decision`, href: '/activity' };
    if (n) out.push({ ...n, read: read.has(n.id) });
  }
  for (const node of nodes) {
    if (node.status !== 'offline') continue;
    const id = `node:${node.node_id}:offline:${node.last_seen}`;
    out.push({ id, kind: 'node_offline', severity: 'warning', source: 'fabric', title: `${node.hostname} is offline`, body: 'No heartbeat for over 2 minutes. Its values are the last report.', created: node.last_seen, href: '/nodes', read: read.has(id) });
  }
  return out.sort((x, y) => Date.parse(y.created) - Date.parse(x.created));
}

/**
 * Activity until the audit route lands (§12, CORE-SEC-6): each action's request, decision and
 * result, oldest first numbered. Not hash-chained, and the screen says so.
 */
export function activityFrom(actions: Action[], names: (id: string) => string): AuditEntry[] {
  type Row = Omit<AuditEntry, 'seq'>;
  const rows: Row[] = [];
  for (const a of actions) {
    const d = describe(a, names);
    const app = d.subject;
    const appId = appIdOf(a);
    const verb = VERB[a.type] ? d.verb.toLowerCase() : d.verb;
    const who = a.requested_by ?? { id: 'unknown requester', kind: 'person' as const };
    if (a.created_at) rows.push({ at: a.created_at, actor: { id: who.id, kind: requesterKind(who.kind) }, kind: 'request', text: `asked to ${verb} ${app}`.trim(), app: appId, hash: '' });
    if (a.decided_by && (a.decided_at ?? a.updated_at)) {
      const denied = a.state === 'cancelled';
      rows.push({ at: (a.decided_at ?? a.updated_at)!, actor: { id: a.decided_by.id, kind: a.decided_by.kind }, kind: 'decision', text: `${denied ? 'denied' : 'approved'}: ${verb} ${app}`.trim(), app: appId, result: denied ? 'info' : 'ok', resultLabel: denied ? 'Denied' : 'Approved', hash: '' });
    }
    const end = a.updated_at;
    if (end && (a.state === 'succeeded' || a.state === 'failed' || a.state === 'outcome_unknown' || a.state === 'expired')) {
      const ok = a.state === 'succeeded';
      const label = ok ? 'Done' : a.state === 'expired' ? 'Expired' : a.state === 'failed' ? 'Failed' : 'Outcome unknown';
      rows.push({ at: end, actor: { id: 'system:executor', kind: 'system' }, kind: 'result', text: `${`${verb} ${app}`.trim()}${a.result?.message && !ok ? `: ${a.result.message}` : ''}`, app: appId, result: ok ? 'ok' : a.state === 'expired' ? 'info' : 'bad', resultLabel: label, hash: '' });
    }
  }
  rows.sort((x, y) => Date.parse(x.at) - Date.parse(y.at));
  return rows.map((r, i) => ({ ...r, seq: i + 1 }));
}

/** Home's "Activity" widget items, newest first. */
export function homeActivity(entries: AuditEntry[]): ActivityItem[] {
  return [...entries].reverse().map((e) => ({
    seq: e.seq,
    at: e.at,
    actor: { kind: e.actor.kind === 'agent' ? 'agent' : e.actor.kind === 'person' ? 'person' : 'system', name: e.actor.id },
    text: e.text,
    result: e.result && e.resultLabel ? { tone: e.result, label: e.resultLabel } : undefined,
  }));
}

export function toPaletteApp(a: CatalogApp): PaletteApp {
  const s = runState(a.status);
  return {
    id: a.id,
    name: nameOf(a),
    category: categorySlug(a.category) ?? a.category ?? '',
    tagline: a.description ?? undefined,
    installed: a.installed,
    status: s === 'installed' || s === 'starting' || s === 'unhealthy' ? s : undefined,
    deployClass: deployClass(a.tier),
  };
}

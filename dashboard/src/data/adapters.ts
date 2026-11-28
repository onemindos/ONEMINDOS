// SPDX-License-Identifier: Apache-2.0
// Contract shapes (sdk/contracts/poc-v0.md §2, §3, §11.4) → the props @onemind/ui renders.
// Pure functions, so every mapping is unit-tested without a browser. Nothing here invents data
// the gateway did not send: a field the contract lacks stays undefined and the ui component
// says "unknown" or "not reported".
import {
  CATEGORY_BY_SLUG,
  type ActionPlan,
  type ActionSummary,
  type PlanEffect,
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

/**
 * The Market licence class (#173). The manifest's declared class is the authority; the gate's scan
 * record can only make it stricter, and only when it was recorded for the current manifest licence.
 * `unknown` is never shown as green. An older gateway that sends no class falls back to the scan record.
 */
export function licenceClassOf(a: CatalogApp): NonNullable<StoreApp['licence_class']> {
  const seen = a.scan?.licence;
  const scanned = seen && seen.spdx === a.license ? seen.class : undefined;
  const declared = a.licence_class;
  if (declared === undefined) return scanned ?? 'L?';
  if (declared === 'unknown') return 'L?';
  return declared === 'blocked' || scanned === 'blocked' ? 'blocked' : declared;
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
    licence_class: licenceClassOf(a),
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
 * Where "Open" goes: the app's own name on the box, `<app>.<box host>`, which the gateway proxies
 * behind the OneMind sign-in (UMB-P02). Never the app's raw port: that skips the sign-in.
 * Only a page served from a `.local` name can say it (onemind.local or <box>.local); from an IP
 * address or any other name there is no app name that resolves, so there is no link.
 */
export function openUrl(a: Pick<CatalogApp, 'id' | 'web_port' | 'installed'>, loc: Pick<Location, 'protocol' | 'hostname'> = window.location): string | undefined {
  if (!a.installed || !a.web_port) return undefined;
  const host = loc.hostname.toLowerCase();
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)*\.local$/.test(host) || !/^[a-z0-9-]+$/.test(a.id)) return undefined;
  return `${loc.protocol}//${a.id}.${host}/`;
}

/** Gateway app `status` → run state. `installed` means applied, not "healthy": v0 reports no health. */
export function runState(status: string): AppRunState & InstalledRunState {
  switch (status) {
    case 'stopped':
      return 'stopped';
    case 'starting':
    case 'stopping':
    case 'restarting':
    case 'configuring':
      return 'starting';
    case 'updating':
      return 'updating';
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

/** Shown when an app is installed but this page's address cannot name it (an IP address, say). */
export const NO_APP_NAME_NOTE = 'open the dashboard at onemind.local to open apps behind the OneMind sign-in';

/** An installed app for the manager. The hub reports no node or health per app in v0. */
export function toInstalled(a: CatalogApp, checkedAt: string, loc?: Pick<Location, 'protocol' | 'hostname'>): InstalledApp {
  const url = openUrl(a, loc);
  return {
    app: toStoreApp(a),
    node: 'this OneMind (the hub places it)',
    state: runState(a.status),
    checked_at: checkedAt,
    url,
    url_note: !url && a.installed && a.web_port ? NO_APP_NAME_NOTE : undefined,
  };
}

const finite = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

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
    // The heartbeat nests these under `metrics`; Home reads them flat. Missing stays null, never 0.
    cpu_percent: finite(n.metrics?.cpu_pct),
    temp_c: finite(n.metrics?.temp_c),
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

/** The display name of a principal, when known (people from /v1/users, agents from /v1/agents). */
export type PrincipalName = (who: { id: string; kind: string }) => string | undefined;

/**
 * Names for the principals on an approval: a person's display name from the users list, an agent's
 * name from the agents list or its 'agent:<name>' id. Unknown ids stay as they are (no guessing).
 */
export function principalNamer(users: ReadonlyArray<{ id: string; display_name: string }>, agents: ReadonlyArray<{ id: string }>): PrincipalName {
  const people = new Map(users.map((u) => [u.id, u.display_name]));
  const bots = new Set(agents.map((g) => g.id));
  return (who) => {
    if (who.kind === 'person') return people.get(who.id) || undefined;
    const bare = who.id.startsWith('agent:') ? who.id.slice('agent:'.length) : who.id;
    return bots.has(bare) || who.id.startsWith('agent:') ? bare : undefined;
  };
}

export function toActionSummary(a: Action, appName?: (id: string) => string, nameOf?: PrincipalName): ActionSummary {
  const rb = a.requested_by;
  const db = a.decided_by;
  const params = a.params;
  const { app_id: appId, display_name: personName, wait_days: wait, cooling_off_days: coolingOff } = params as Record<string, unknown>;
  const familyInvite = ['users.invite', 'users.reinvite'].includes(a.type);
  const impact = a.type === 'legacy.contact.add' && typeof wait === 'number' && typeof coolingOff === 'number'
    ? `After a ${coolingOff}-day cooling-off period, this contact can file a claim after your death. If you remain inactive during the ${wait}-day claim wait and a second person confirms when available, the contact has 12 months to download a read-only export of your personal files.`
    : undefined;
  return {
    target_name: familyInvite && typeof personName === 'string' ? personName
      : appName && typeof appId === 'string' ? appName(appId) : undefined,
    id: a.id,
    type: a.type,
    params,
    impact,
    state: a.state,
    expires_at: a.expires_at,
    hold: a.approval?.hold ? { duration: Math.max(2000, a.approval.hold_ms ?? 2000), plan: a.plan_sha256 } : undefined,
    physical: a.approval?.physical || undefined,
    created_at: a.created_at,
    requested_by: rb ? { id: rb.id, kind: requesterKind(rb.kind), role: rb.role, name: nameOf?.(rb) } : undefined,
    decided_by: db ? { id: db.id, kind: db.kind, name: nameOf?.(db) } : undefined,
    message: RESULT_MESSAGE.has(a.state) ? (a.result?.message ?? undefined) : undefined,
    // D-028: the key level approving needs, from the hub's read model; the card shows "Needs L2" from it.
    required_level: a.required_level ?? undefined,
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
    type: a.type as StoreJob['type'],
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
  const machine = (a.params as Record<string, unknown> | undefined)?.name;
  const subject = appId ? names(appId) : typeof machine === 'string' ? machine : typeof nodeId === 'string' ? nodeId : '';
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

/** The gateway plan's own warning that the network path effects already say. */
const NETWORK_WARNING = /^Opens a network path/;

/**
 * The gateway's plan (summary, objects, volumes, warnings, network paths; lifecycle.py) as the
 * plain-language effects card: what is kept or deleted, which ports and paths open, and what the
 * gateway warns about. Nothing is invented: a plan with no volumes or paths says no changes beyond
 * the action itself. Undefined when the action has no plan (the board then says so).
 */
export function toActionPlan(a: Action): ActionPlan | undefined {
  const p = a.plan as Record<string, unknown> | null | undefined;
  if (!p || !a.plan_sha256) return undefined;
  const list = (v: unknown): Array<Record<string, unknown>> => (Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : []);
  const effects: PlanEffect[] = [];
  for (const v of list(p.volumes)) {
    if (v.effect === 'deleted') effects.push({ kind: 'data-delete', risk: 'high', label: 'Deletes all of this app\'s files and databases', detail: 'No undo' });
    else if (v.effect === 'kept') effects.push({ kind: 'volume', risk: 'low', label: 'Keeps this app\'s files and databases', detail: 'Your data stays on disk' });
    else effects.push({ kind: 'volume', risk: 'medium', label: `Changes stored data (${String(v.effect ?? 'unknown')})` });
  }
  for (const n of list(p.network_paths)) {
    effects.push({ kind: 'port', risk: 'medium', label: `Opens a path from ${String(n.from)} to ${String(n.to)}`, detail: `TCP port ${String(n.port)}${n.requirement ? `, needs ${String(n.requirement)}` : ''}` });
  }
  for (const w of Array.isArray(p.warnings) ? p.warnings : []) {
    if (typeof w === 'string' && !NETWORK_WARNING.test(w)) effects.push({ kind: 'note', risk: /no undo|deleted|refus/i.test(w) ? 'high' : 'low', label: w });
  }
  if (typeof p.summary === 'string' && p.summary) effects.unshift({ kind: 'note', risk: 'low', label: p.summary });
  const preview = a.approval?.physical ? a.approval.preview : undefined;
  if (preview?.kind === 'text' && preview.text) effects.unshift({ kind: 'note', risk: 'high', label: preview.text });
  // AIG-04 (#168): the requester read third-party text before asking (core taint.py). Shown first.
  const taint = p.taint as { sources?: unknown; message?: unknown } | null | undefined;
  if (taint && typeof taint === 'object') {
    const read = Array.isArray(taint.sources) ? taint.sources.filter((x): x is string => typeof x === 'string') : [];
    effects.unshift({
      kind: 'note', risk: 'high',
      label: typeof taint.message === 'string' && taint.message ? taint.message : 'This agent read text written by third parties before asking.',
      ...(read.length ? { detail: `What it read: ${read.join(', ')}` } : {}),
    });
  }
  return {
    action_id: a.id,
    plan_hash: a.plan_sha256,
    computed_at: a.created_at ?? new Date(0).toISOString(),
    effects,
    undo: a.type === ('app.delete_data' as string) ? 'one-way' : 'reversible',
  };
}

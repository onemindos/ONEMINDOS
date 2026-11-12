// SPDX-License-Identifier: Apache-2.0
// Command palette logic (backlog UX-P3): build commands from typed data, rank them, group them.
// Every command maps to an API or CLI call (`equivalent`, P4). Commands that change something
// never act directly: they create a request that waits in Approvals (P1).
import type { Tone } from '../tokens/tokens';
import type { ActionSummary } from '../components/ApprovalCard';
import { actionTitle } from '../components/ApprovalCard';
import type { NodeSummary } from '../components/NodeCard';
import { freshness, FRESHNESS_LABEL, FRESHNESS_TONE } from '../lib/freshness';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import type { ShellIconName } from './icons';
import { category, deployClass, deployClassLabel, type DeployClass } from './taxonomy';

export const COMMAND_GROUPS = ['Approvals', 'Recent', 'Apps', 'Requests', 'Nodes', 'Settings', 'Go to'] as const;
export type CommandGroup = (typeof COMMAND_GROUPS)[number];

export interface PaletteCommand {
  id: string;
  group: Exclude<CommandGroup, 'Recent'>;
  title: string;
  subtitle?: string;
  keywords?: string[];
  icon: ShellIconName;
  /** Where it goes. A request command has no href: running it creates the request. */
  href?: string;
  /** Creates an action (contract §3) that waits for the owner. */
  request?: { type: string; params: Record<string, unknown> };
  /** The same thing from a terminal or the API (UX-B2). */
  equivalent?: string;
  pill?: { tone: Tone; label: string };
  /** Shown instead of running; the option stays visible (IA §4 Forbidden). */
  disabledReason?: string;
}

/** Scope prefixes: "> " searches only requests, "@" only nodes, "#" a category. */
export interface ParsedQuery {
  scope: 'all' | 'requests' | 'nodes' | 'category';
  text: string;
}

export function parseQuery(raw: string): ParsedQuery {
  const q = raw.trimStart();
  if (q.startsWith('>')) return { scope: 'requests', text: q.slice(1).trim() };
  if (q.startsWith('@')) return { scope: 'nodes', text: q.slice(1).trim() };
  if (q.startsWith('#')) return { scope: 'category', text: q.slice(1).trim() };
  return { scope: 'all', text: q.trim() };
}

const norm = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');

/** Score one token against one string: prefix > word start > substring > in-order letters. */
function scoreToken(token: string, hay: string): number {
  if (!token) return 1;
  const h = norm(hay);
  if (h.startsWith(token)) return 100;
  if (new RegExp(`(^|[\\s\\-_./:·])${token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`).test(h)) return 80;
  if (h.includes(token)) return 55;
  // in-order letters ("hass" → "home assistant"); tighter spans score higher
  let i = 0;
  let first = -1;
  for (let j = 0; j < h.length && i < token.length; j++) {
    if (h[j] === token[i]) {
      if (first < 0) first = j;
      i++;
    }
  }
  if (i < token.length) return 0;
  return Math.max(5, 30 - (h.length - token.length) / 2 - first);
}

/** 0 means "no match". Every word of the query must match the title, subtitle or a keyword. */
export function scoreCommand(cmd: PaletteCommand, text: string): number {
  const tokens = norm(text).split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return 1;
  let total = 0;
  for (const t of tokens) {
    const best = Math.max(
      scoreToken(t, cmd.title) * 1.2,
      cmd.subtitle ? scoreToken(t, cmd.subtitle) * 0.6 : 0,
      ...(cmd.keywords ?? []).map((k) => scoreToken(t, k) * 0.8),
    );
    if (best === 0) return 0;
    total += best;
  }
  return total;
}

export interface ResultGroup {
  group: CommandGroup;
  items: PaletteCommand[];
}

export interface SearchOptions {
  /** Recently run command ids, newest first; shown on an empty query. */
  recent?: string[];
  /** Max items per group. */
  limit?: number;
}

/** Ranked, grouped results. An empty query shows approvals, recent commands, then navigation. */
export function searchCommands(all: PaletteCommand[], raw: string, { recent = [], limit = 6 }: SearchOptions = {}): ResultGroup[] {
  const { scope, text } = parseQuery(raw);
  let pool = all;
  if (scope === 'requests') pool = all.filter((c) => c.request);
  if (scope === 'nodes') pool = all.filter((c) => c.group === 'Nodes');
  if (scope === 'category') pool = all.filter((c) => c.group === 'Apps' || c.group === 'Requests');

  if (!text && scope === 'all') {
    const byId = new Map(all.map((c) => [c.id, c]));
    const rec = recent.map((id) => byId.get(id)).filter((c): c is PaletteCommand => !!c && c.group !== 'Approvals');
    const out: ResultGroup[] = [
      { group: 'Approvals', items: all.filter((c) => c.group === 'Approvals').slice(0, limit) },
      { group: 'Recent', items: rec.slice(0, 4) },
      { group: 'Go to', items: all.filter((c) => c.group === 'Go to').slice(0, 8) },
    ];
    return out.filter((g) => g.items.length > 0);
  }

  const scored = pool
    .map((c) => ({ c, s: scope === 'category' ? scoreCategory(c, text) : scoreCommand(c, text) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.c.title.localeCompare(b.c.title));
  const groups = new Map<CommandGroup, PaletteCommand[]>();
  for (const { c } of scored) {
    const xs = groups.get(c.group) ?? [];
    if (xs.length < limit) xs.push(c);
    groups.set(c.group, xs);
  }
  // Group order follows the best hit, so the top match is always first on screen.
  return Array.from(groups, ([group, items]) => ({ group, items }));
}

function scoreCategory(c: PaletteCommand, text: string): number {
  const cat = c.keywords?.[0];
  if (!cat) return 0;
  if (!text) return 1;
  const meta = category(cat);
  return Math.max(scoreToken(norm(text), cat), meta ? scoreToken(norm(text), meta.name) : 0);
}

/** Flatten for keyboard movement (the listbox's option order). */
export function flatten(groups: ResultGroup[]): PaletteCommand[] {
  return groups.flatMap((g) => g.items);
}

/** Next active index for ArrowUp/ArrowDown/Home/End, wrapping, skipping nothing (disabled options stay reachable so their reason is read). */
export function moveActive(current: number, key: string, count: number): number {
  if (count === 0) return -1;
  switch (key) {
    case 'ArrowDown':
      return (current + 1) % count;
    case 'ArrowUp':
      return current <= 0 ? count - 1 : current - 1;
    case 'Home':
      return 0;
    case 'End':
      return count - 1;
    default:
      return current;
  }
}

/** Cmd-K on macOS, Ctrl-K elsewhere. */
export function isPaletteHotkey(e: Pick<KeyboardEvent, 'key' | 'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey'>): boolean {
  return e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey;
}

/** Push to a most-recent-first list without duplicates. */
export function pushRecent(recent: string[], id: string, max = 8): string[] {
  return [id, ...recent.filter((r) => r !== id)].slice(0, max);
}

// ---------- building commands from typed data ----------

export interface PaletteApp {
  id: string;
  name: string;
  category: string;
  tagline?: string;
  installed: boolean;
  status?: 'running' | 'installed' | 'starting' | 'stopped' | 'unhealthy';
  deployClass?: DeployClass;
  plugin?: boolean;
  updateAvailable?: string;
}

export interface PaletteData {
  now: number;
  apps: PaletteApp[];
  nodes: NodeSummary[];
  pending: ActionSummary[];
  /** Whether the viewer can approve (owner). Agents and guests see the reason instead. */
  canApprove: boolean;
}

const APP_STATUS: Record<NonNullable<PaletteApp['status']>, { tone: Tone; label: string }> = {
  running: { tone: 'ok', label: 'Running' },
  installed: { tone: 'info', label: 'Installed' },
  starting: { tone: 'info', label: 'Starting' },
  stopped: { tone: 'neutral', label: 'Stopped' },
  unhealthy: { tone: 'bad', label: 'Unhealthy' },
};

export const SETTINGS_COMMANDS: PaletteCommand[] = [
  { id: 'set:appearance', group: 'Settings', title: 'Appearance', subtitle: 'Theme, accent colour and wallpaper', keywords: ['theme', 'dark', 'light', 'accent', 'wallpaper', 'colour', 'color'], icon: 'brush', href: '#/settings/appearance', equivalent: 'onemind settings appearance' },
  { id: 'set:people', group: 'Settings', title: 'People', subtitle: 'Who can sign in, and their roles', keywords: ['users', 'invite', 'family', 'owner'], icon: 'user', href: '#/settings/people', equivalent: 'GET /v1/auth/principals' },
  { id: 'set:passkeys', group: 'Settings', title: 'Passkeys and sessions', subtitle: 'Sign-in devices and open sessions', keywords: ['login', 'password', 'security', 'session', 'totp'], icon: 'passkey', href: '#/settings/security', equivalent: 'GET /v1/auth/sessions' },
  { id: 'set:agents', group: 'Settings', title: 'Agents and tokens', subtitle: 'What each agent may request', keywords: ['ai', 'token', 'mcp', 'scope'], icon: 'agent', href: '#/settings/agents', equivalent: 'GET /v1/auth/tokens' },
  { id: 'set:notifications', group: 'Settings', title: 'Notification routes', subtitle: 'Phone, email, quiet hours', keywords: ['alerts', 'push', 'ntfy', 'quiet'], icon: 'bell', href: '#/settings/notifications', equivalent: 'GET /v1/notify/routes' },
  { id: 'set:remote', group: 'Settings', title: 'Remote access', subtitle: 'Reach the box away from home', keywords: ['vpn', 'internet', 'expose', 'mesh'], icon: 'globe', href: '#/settings/remote', equivalent: 'onemind remote status' },
  { id: 'set:backups', group: 'Settings', title: 'Backup destinations and emergency kit', keywords: ['restore', 'usb', 's3', 'recovery key'], icon: 'backups', href: '#/backups', equivalent: 'GET /v1/backups' },
];

export const NAV_COMMANDS: PaletteCommand[] = [
  { id: 'go:home', group: 'Go to', title: 'Home', icon: 'home', href: '#/home', keywords: ['dashboard', 'start'] },
  { id: 'go:apps', group: 'Go to', title: 'Apps and Market', icon: 'apps', href: '#/apps', keywords: ['store', 'install', 'market'] },
  { id: 'go:approvals', group: 'Go to', title: 'Approvals', icon: 'approvals', href: '#/approvals', keywords: ['requests', 'pending'] },
  { id: 'go:activity', group: 'Go to', title: 'Activity', icon: 'activity', href: '#/activity', keywords: ['audit', 'log', 'history'] },
  { id: 'go:alerts', group: 'Go to', title: 'Alerts', icon: 'bell', href: '#/notifications', keywords: ['notifications', 'inbox'] },
  { id: 'go:nodes', group: 'Go to', title: 'Nodes', icon: 'nodes', href: '#/nodes', keywords: ['machines', 'fabric', 'servers'] },
  { id: 'go:backups', group: 'Go to', title: 'Backups', icon: 'backups', href: '#/backups', keywords: ['restore', 'snapshot'] },
  { id: 'go:updates', group: 'Go to', title: 'Updates', icon: 'updates', href: '#/updates', keywords: ['upgrade', 'release', 'version'] },
  { id: 'go:settings', group: 'Go to', title: 'Settings', icon: 'settings', href: '#/settings', keywords: ['preferences'] },
];

export function buildCommands(d: PaletteData): PaletteCommand[] {
  const out: PaletteCommand[] = [];

  for (const a of d.pending.filter((p) => p.state === 'awaiting_approval')) {
    // Same rule as ApprovalCard: a `system:` principal is the box itself, never shown as an agent.
    const rb = a.requested_by;
    const kindLabel = rb?.id.startsWith('system:') ? 'System' : rb?.kind === 'agent' ? 'Agent' : 'Person';
    const who = rb ? `${kindLabel} ${rb.id.split(':')[1] ?? rb.id}` : 'Unknown requester';
    out.push({
      id: `approval:${a.id}`,
      group: 'Approvals',
      title: `Review: ${actionTitle(a)}`,
      subtitle: `${who} · expires ${formatIn(a.expires_at, d.now)}`,
      keywords: ['approve', 'deny', a.type],
      icon: 'approvals',
      href: `#/approvals/${encodeURIComponent(a.id)}`,
      equivalent: `GET /v1/actions/${a.id}`,
      pill: { tone: 'warn', label: 'Waiting' },
      disabledReason: d.canApprove ? undefined : 'Only the owner can approve. You can still read it.',
    });
  }

  for (const app of d.apps) {
    const cat = category(app.category);
    const kw = [app.category, cat?.name ?? '', app.id];
    if (app.installed) {
      const st = app.status ? APP_STATUS[app.status] : { tone: 'neutral' as Tone, label: 'Unknown' };
      out.push({
        id: `app:${app.id}`,
        group: 'Apps',
        title: app.name,
        subtitle: [cat?.name, app.tagline].filter(Boolean).join(' · '),
        keywords: kw,
        icon: cat?.icon ?? 'apps',
        href: `#/app/${encodeURIComponent(app.id)}`,
        equivalent: `onemind apps open ${app.id}`,
        pill: st,
      });
      out.push({
        id: `req:restart:${app.id}`,
        group: 'Requests',
        title: `Request restart of ${app.name}`,
        keywords: [...kw, 'restart', 'reboot'],
        icon: 'updates',
        request: { type: 'app.restart', params: { app_id: app.id } },
        equivalent: `POST /v1/actions {"type":"app.restart","params":{"app_id":"${app.id}"}}`,
      });
      if (app.updateAvailable) {
        out.push({
          id: `req:update:${app.id}`,
          group: 'Requests',
          title: `Request update of ${app.name} to ${app.updateAvailable}`,
          keywords: [...kw, 'update', 'upgrade'],
          icon: 'download',
          request: { type: 'app.update', params: { app_id: app.id, to: app.updateAvailable } },
          equivalent: `POST /v1/actions {"type":"app.update","params":{"app_id":"${app.id}","to":"${app.updateAvailable}"}}`,
          pill: { tone: 'info', label: 'Update' },
        });
      }
    } else {
      const cls = app.deployClass ?? 'market-verified';
      const meta = deployClass(cls);
      const pill = { tone: meta.tone, label: deployClassLabel(cls, app.plugin) };
      if (!meta.requestable) {
        // Link-only and core apps are never requested from here: open the page, say why.
        out.push({
          id: `app:${app.id}`,
          group: 'Apps',
          title: app.name,
          subtitle: [cat?.name, `${meta.label}: ${meta.sentence}`].filter(Boolean).join(' · '),
          keywords: kw,
          icon: cat?.icon ?? 'apps',
          href: `#/app/${encodeURIComponent(app.id)}`,
          equivalent: `onemind apps show ${app.id}`,
          pill,
        });
        continue;
      }
      out.push({
        id: `req:install:${app.id}`,
        group: 'Requests',
        title: `Request install of ${app.name}`,
        subtitle: [cat?.name, app.tagline, cls === 'market-community' ? 'Not fully checked by OneMind' : undefined].filter(Boolean).join(' · '),
        keywords: [...kw, 'install', 'add'],
        icon: cat?.icon ?? 'apps',
        request: { type: 'app.install', params: { app_id: app.id } },
        equivalent: `POST /v1/actions {"type":"app.install","params":{"app_id":"${app.id}"}}`,
        pill,
      });
    }
  }

  for (const n of d.nodes) {
    const age = secondsSince(n.last_seen, d.now);
    const f = n.status === 'online' ? 'live' : (n.status ?? freshness(age));
    out.push({
      id: `node:${n.node_id}`,
      group: 'Nodes',
      title: n.hostname,
      subtitle: `${n.role === 'hub' ? 'Hub' : 'Node'} · ${n.arch} · last report ${formatAgo(age)}`,
      keywords: [n.board, n.arch, n.role, 'machine', 'node'],
      icon: 'nodes',
      href: `#/nodes/${encodeURIComponent(n.node_id)}`,
      equivalent: `GET /v1/nodes/${n.node_id}`,
      pill: { tone: FRESHNESS_TONE[f], label: FRESHNESS_LABEL[f] },
    });
  }

  return [...out, ...SETTINGS_COMMANDS, ...NAV_COMMANDS];
}

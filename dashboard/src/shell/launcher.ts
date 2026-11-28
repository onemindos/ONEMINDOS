// SPDX-License-Identifier: Apache-2.0
// The Atlas launcher's logic (final design 03): one search across apps, system screens, machines and commands,
// a best match, and for every command the exact `onemind` line (the same command works in a terminal, over SSH and
// in the run bar). Commands that change something never act here: they file a request that waits for a person.
import { scorePaletteCommand, type NavItem, type PaletteCommand } from '@onemind/ui';
import type { NodeStatus } from '../api/types';

export type LauncherKind = 'apps' | 'system' | 'machines' | 'commands';
export type LauncherScope = 'all' | LauncherKind;

export const SCOPE_LABEL: Record<LauncherScope, string> = { all: 'Everything', apps: 'Apps', system: 'System', machines: 'Machines', commands: 'Commands' };

export interface LauncherMachine {
  id: string;
  name: string;
  status: NodeStatus;
}

export interface LauncherApp {
  id: string;
  name: string;
  icon?: string | null;
  href: string;
}

export interface LauncherItem {
  key: string;
  kind: LauncherKind;
  title: string;
  subtitle?: string;
  keywords?: string[];
  href?: string;
  nav?: NavItem;
  app?: LauncherApp;
  machine?: LauncherMachine;
  command?: PaletteCommand;
}

export interface LauncherData {
  nav: NavItem[];
  apps: LauncherApp[];
  machines: LauncherMachine[];
  commands: PaletteCommand[];
}

/** The state word a machine shows (Atlas: fresh, stale, offline). */
export const MACHINE_WORD: Record<NodeStatus, string> = { online: 'fresh', stale: 'stale', offline: 'offline' };

/** A command the launcher lists: it changes something (a request) or has a command line to show. */
function listsCommand(c: PaletteCommand): boolean {
  return !!c.request || !!c.equivalent;
}

/** The exact command, "$ onemind ..." when the CLI has one; otherwise the API call it makes. */
export function commandLine(c: PaletteCommand): { cli: boolean; text: string } | undefined {
  if (!c.equivalent) return undefined;
  return c.equivalent.startsWith('onemind ') ? { cli: true, text: `$ ${c.equivalent}` } : { cli: false, text: c.equivalent };
}

/** Requests go to Approvals: a person decides before anything runs (D-027). */
export const asksAPerson = (c: PaletteCommand) => !!c.request;

export function launcherItems(d: LauncherData): LauncherItem[] {
  const out: LauncherItem[] = [];
  for (const a of d.apps) out.push({ key: `app:${a.id}`, kind: 'apps', title: a.name, keywords: [a.id], href: a.href, app: a });
  for (const n of d.nav) out.push({ key: `nav:${n.id}`, kind: 'system', title: n.label, keywords: [n.id], href: n.href, nav: n });
  for (const m of d.machines) out.push({ key: `machine:${m.id}`, kind: 'machines', title: m.name, subtitle: MACHINE_WORD[m.status], keywords: [m.id, 'machine', 'node'], href: '/nodes', machine: m });
  for (const c of d.commands.filter(listsCommand)) out.push({ key: `cmd:${c.id}`, kind: 'commands', title: c.title, subtitle: c.subtitle, keywords: [...(c.keywords ?? []), c.equivalent ?? ''], command: c });
  return out;
}

function score(item: LauncherItem, text: string): number {
  return scorePaletteCommand({ id: item.key, group: 'Go to', icon: 'apps', title: item.title, subtitle: item.subtitle, keywords: item.keywords }, text);
}

export interface LauncherResult {
  /** The top matches across every kind (only while typing). Enter opens the first. */
  best: LauncherItem[];
  /** Per kind, ranked when typing, in their natural order otherwise. */
  groups: Record<LauncherKind, LauncherItem[]>;
  /** How many of each kind exist at all (the pill counts). */
  counts: Record<LauncherKind, number>;
}

const KINDS: readonly LauncherKind[] = ['apps', 'system', 'machines', 'commands'];

export function searchLauncher(items: LauncherItem[], query: string, scope: LauncherScope = 'all', bestCount = 5): LauncherResult {
  const text = query.trim();
  const counts = Object.fromEntries(KINDS.map((k) => [k, items.filter((i) => i.kind === k).length])) as Record<LauncherKind, number>;
  const pool = scope === 'all' ? items : items.filter((i) => i.kind === scope);
  const ranked = text
    ? pool
        .map((i) => ({ i, s: score(i, text) }))
        .filter((x) => x.s > 0)
        .sort((a, b) => b.s - a.s || a.i.title.localeCompare(b.i.title))
        .map((x) => x.i)
    : pool;
  const groups = Object.fromEntries(KINDS.map((k) => [k, ranked.filter((i) => i.kind === k)])) as Record<LauncherKind, LauncherItem[]>;
  return { best: text ? ranked.slice(0, bestCount) : [], groups, counts };
}

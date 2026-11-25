// SPDX-License-Identifier: Apache-2.0
// The screen registry. Every file src/screens/<id>/screen.ts is one screen; every file
// src/screens/settings-pages/<id>.ts is one Settings sub-page. Vite's import.meta.glob finds them at
// build time, so adding a screen touches no shared list ("How to add a screen" in dashboard/README.md).
import type { NavItem } from '@onemind/ui';
import type { ScreenDef, SettingsPageDef } from './types';

const screenFiles = import.meta.glob<{ default: ScreenDef }>('./*/screen.ts', { eager: true });
const settingsFiles = import.meta.glob<{ default: SettingsPageDef }>('./settings-pages/*.ts', { eager: true });

/** file path → definition, for the registry test. */
export const SCREEN_FILES: Record<string, ScreenDef | undefined> = Object.fromEntries(Object.entries(screenFiles).map(([f, m]) => [f, m.default]));
export const SETTINGS_FILES: Record<string, SettingsPageDef | undefined> = Object.fromEntries(Object.entries(settingsFiles).map(([f, m]) => [f, m.default]));

/** Every screen, in nav order. */
export const SCREENS: readonly ScreenDef[] = Object.values(SCREEN_FILES)
  .filter((s): s is ScreenDef => !!s)
  .sort((a, b) => a.order - b.order);

export const SETTINGS_PAGES: ReadonlyMap<string, SettingsPageDef> = new Map(
  Object.values(SETTINGS_FILES)
    .filter((s): s is SettingsPageDef => !!s)
    .map((s) => [s.id, s]),
);

/** Nav ids of the Pro screens (shell/roles.ts). */
export const PRO_SCREEN_IDS: ReadonlySet<string> = new Set(SCREENS.filter((s) => s.pro).map((s) => s.id));

/** Docked screens, in dock order. */
export const DOCK_ORDER: readonly string[] = SCREENS.filter((s) => s.dock !== undefined)
  .sort((a, b) => a.dock! - b.dock!)
  .map((s) => s.id);

export const HUES: Readonly<Record<string, readonly [string, string]>> = Object.fromEntries(SCREENS.map((s) => [s.id, s.hue]));

const firstSegment = (path: string) => path.split('/').filter(Boolean)[0] ?? 'home';

/** The screen a pathname belongs to (a detail page or tab counts), as a nav id. */
export function navIdFor(pathname: string): string {
  const seg = firstSegment(pathname);
  const owner = SCREENS.find((s) => [s.path, ...(s.extra ?? []).map((e) => e.path)].some((p) => firstSegment(p) === seg));
  return owner?.id ?? seg;
}

/** The sidebar / Launchpad items; `waiting` fills the Approvals badge. */
export function navItems(waiting: number): NavItem[] {
  return SCREENS.filter((s) => !s.hidden).map((s) => {
    const item: NavItem = { id: s.id, label: s.title, href: s.path, icon: s.icon };
    if (s.section === 'primary') item.primary = true;
    else item.group = s.section;
    if (s.badge === 'approvals') {
      item.badge = waiting;
      item.badgeLabel = `${waiting} waiting`;
    }
    return item;
  });
}

/** Problems with a set of screen definitions: missing fields, duplicate ids or paths. Empty when sound. */
export function screenProblems(defs: Record<string, ScreenDef | undefined>): string[] {
  const out: string[] = [];
  const ids = new Map<string, string>();
  const paths = new Map<string, string>();
  const claim = (map: Map<string, string>, key: string, file: string, what: string) => {
    const prev = map.get(key);
    if (prev) out.push(`${what} "${key}" is claimed by both ${prev} and ${file}`);
    else map.set(key, file);
  };
  for (const [file, d] of Object.entries(defs)) {
    if (!d) {
      out.push(`${file}: no default export`);
      continue;
    }
    for (const k of ['id', 'path', 'title', 'icon', 'section', 'order', 'hue', 'load'] as const) if (d[k] === undefined || d[k] === '') out.push(`${file}: missing "${k}"`);
    if (typeof d.id !== 'string' || typeof d.path !== 'string') continue;
    if (!file.startsWith(`./${d.id}/`)) out.push(`${file}: id "${d.id}" must match the folder name`);
    if (!d.path.startsWith('/')) out.push(`${file}: path "${d.path}" must start with "/"`);
    claim(ids, d.id, file, 'id');
    for (const p of [d.path, ...(d.extra ?? []).map((e) => e.path)]) claim(paths, p.replace(/^\//, ''), file, 'path');
    for (const r of d.redirects ?? []) claim(paths, r.from.replace(/^\//, ''), file, 'path');
  }
  return out;
}

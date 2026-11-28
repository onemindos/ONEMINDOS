// SPDX-License-Identifier: Apache-2.0
// The Atlas dock (final design 01, DESIGN.md "Dock"): the OneMind logo tile first (it opens the launcher), then the
// pinned places in the screens' `dock` order (Home, Map, Approvals, Files, Market, Backups, Machines), then running
// windows without a pin, then pinned apps, then the run bar when the person switched it on. The run bar needs room:
// the last pinned apps move into a "More" item that names them, so nothing leaves the dock silently.
import type { NavItem } from '@onemind/ui';
import { DOCK_ORDER, SCREENS } from '../screens/registry';

/** The Map screen's path and dock slot. The Map lane registers `screens/map/screen.ts` with `dock: 2`. */
export const MAP_PATH = '/map';
const MAP_SLOT = 1; // zero-based: second, after Home

/**
 * Until the Map screen is registered, the dock still links slot 2 to /map (the router sends an unknown path back to
 * the desktop, so the link is harmless). Once a `map` screen exists its own nav item, title and role gate win.
 */
export const MAP_PLACEHOLDER: NavItem = { id: 'map', label: 'Map', href: MAP_PATH, icon: 'network' };

/** Pinned apps that stay beside the run bar; the rest move into "More". */
export const APPS_BESIDE_RUN_BAR = 2;

/** The dock's place ids in order: the registry's `dock` fields, with Map in slot 2 even before its screen exists. */
export function dockOrder(order: readonly string[] = DOCK_ORDER, mapRegistered = SCREENS.some((s) => s.id === 'map')): string[] {
  if (mapRegistered || order.includes('map')) return [...order];
  const out = [...order];
  out.splice(Math.min(MAP_SLOT, out.length), 0, 'map');
  return out;
}

/** Split the nav into dock items (dock order) and launcher-only items (nav order). */
export function dockSplit(nav: NavItem[], order: readonly string[] = dockOrder(), mapRegistered = SCREENS.some((s) => s.id === 'map')): { dock: NavItem[]; more: NavItem[] } {
  const dock = order.flatMap((id) => {
    const found = nav.filter((n) => n.id === id);
    return found.length || id !== 'map' || mapRegistered ? found : [MAP_PLACEHOLDER];
  });
  const more = nav.filter((n) => !order.includes(n.id));
  return { dock, more };
}

/** With the run bar on, keep the first apps and move the rest into "More" (named, never dropped). */
export function makeRoomForRunBar<T>(apps: readonly T[], runBar: boolean, keep = APPS_BESIDE_RUN_BAR): { shown: T[]; moved: T[] } {
  if (!runBar) return { shown: [...apps], moved: [] };
  return { shown: apps.slice(0, keep), moved: apps.slice(keep) };
}

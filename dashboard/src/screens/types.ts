// SPDX-License-Identifier: Apache-2.0
// What a screen declares about itself. One file per screen (src/screens/<id>/screen.ts, default
// export); registry.ts finds them all with import.meta.glob, and the shell (routes, dock,
// Launchpad, Console sidebar, role gating) reads the registry instead of hand-kept lists.
import type { ComponentType } from 'react';
import type { NavItem, SettingsSectionId } from '@onemind/ui';

/** A lazy page: `() => import('../../pages/Nodes').then((m) => ({ default: m.Nodes }))`. */
export type ScreenLoader = () => Promise<{ default: ComponentType }>;

export interface ScreenDef {
  /** Nav id: also the key of the Pro gate, the dock and the tile colour. Matches the folder name. */
  id: string;
  /** The screen's own path, "/" for the desktop. */
  path: string;
  /** Name in the dock, Launchpad, sidebar, window bar and the "for owners" notice. */
  title: string;
  icon: NavItem['icon'];
  /** Where it is offered: the primary four (phone tab bar), or a sidebar / Launchpad section. */
  section: 'primary' | 'Your box' | 'System';
  /** Position in the sidebar and Launchpad (ascending). Leave gaps of 10 so a new screen fits between two. */
  order: number;
  /**
   * Position in the dock when the screen is docked; omit and it is one click away in the launcher. The Atlas
   * default (final design 01): Home 1, Map 2, Approvals 3, Files 4, Market 5, Backups (Protect) 6, Machines 7.
   */
  dock?: number;
  /** Tile gradient (two colours) with a white glyph on top. */
  hue: readonly [string, string];
  /** Pro-only: offered to owners and adults, guarded by ProOnly (shell/roles.ts). */
  pro?: boolean;
  /** A live count the shell fills in. Only 'approvals' exists: requests awaiting a decision. */
  badge?: 'approvals';
  /**
   * Routed and windowed but never offered as a tile (dock, Launchpad, sidebar): a page reached from another screen
   * or a link (a path with a parameter has no nav entry), or one that only exists to say what is not built yet.
   */
  hidden?: boolean;
  load: ScreenLoader;
  /** More paths of the same screen (a detail page, a tab). Nav and window title stay this screen's. */
  extra?: { path: string; load?: ScreenLoader; /** Owner-only page: guarded by OwnerOnly (shell/ProOnly.tsx), titled with this text. */ owner?: string }[];
  /** Old paths that now live here; they replace-redirect to `to`. */
  redirects?: { from: string; to: string }[];
}

/** One Settings sub-page (src/screens/settings-pages/<id>.ts, default export). */
export interface SettingsPageDef {
  /** A @onemind/ui SETTINGS_SECTIONS id. */
  id: SettingsSectionId;
  /** The page, when this hub serves it. */
  load?: ScreenLoader;
  /** Otherwise, a section a screen of its own serves: the path of that screen. It must match that screen's `redirects`. */
  to?: string;
}

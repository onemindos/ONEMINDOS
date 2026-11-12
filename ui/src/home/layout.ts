// SPDX-License-Identifier: Apache-2.0
// Home layout: which widgets, in which order and size, and which apps sit in the dock.
// Saved per person. Every change is a pure function here, so the layout logic is tested
// without a browser and the same rules apply on the hub when it stores the layout
// (PROPOSED `GET/PUT /v1/people/me/home`; see README.md).
import type { HomeApp } from './types';

export type WidgetSize = 'S' | 'M' | 'L';
export const WIDGET_SIZES: readonly WidgetSize[] = ['S', 'M', 'L'];
export const SIZE_LABEL: Record<WidgetSize, string> = { S: 'Small', M: 'Medium', L: 'Large' };

export type BuiltinKind = 'approvals' | 'system' | 'activity' | 'backups' | 'updates' | 'mesh';
export type WidgetKind = BuiltinKind | 'app';

export interface WidgetInstance {
  /** Unique within the layout. */
  id: string;
  kind: WidgetKind;
  size: WidgetSize;
  /** `system`: one node by node_id; absent = every node. */
  nodeId?: string;
  /** `app`: which app and which of its declared widgets. */
  appId?: string;
  widgetId?: string;
}

export interface HomeLayout {
  version: 1;
  widgets: WidgetInstance[];
  /** App ids in dock order. */
  pinned: string[];
}

export const MAX_WIDGETS = 12;
export const MAX_PINNED = 8;
/** "Needs you" stays first and cannot be removed (P1: approvals are first-class). */
export const LOCKED_KIND: WidgetKind = 'approvals';

export const DEFAULT_LAYOUT: HomeLayout = {
  version: 1,
  widgets: [
    { id: 'w-approvals', kind: 'approvals', size: 'M' },
    { id: 'w-system', kind: 'system', size: 'M' },
    { id: 'w-updates', kind: 'updates', size: 'S' },
    { id: 'w-backups', kind: 'backups', size: 'S' },
    { id: 'w-mesh', kind: 'mesh', size: 'S' },
    { id: 'w-activity', kind: 'activity', size: 'M' },
  ],
  pinned: [],
};

export const isLocked = (w: WidgetInstance) => w.kind === LOCKED_KIND;

/** Move a widget to `to` (0-based). The locked widget and position 0 never move. */
export function moveWidget(layout: HomeLayout, id: string, to: number): HomeLayout {
  const from = layout.widgets.findIndex((w) => w.id === id);
  if (from < 0) return layout;
  const w = layout.widgets[from]!;
  if (isLocked(w)) return layout;
  const firstMovable = layout.widgets[0] && isLocked(layout.widgets[0]) ? 1 : 0;
  const target = Math.max(firstMovable, Math.min(layout.widgets.length - 1, to));
  if (target === from) return layout;
  const next = layout.widgets.slice();
  next.splice(from, 1);
  next.splice(target, 0, w);
  return { ...layout, widgets: next };
}

export function resizeWidget(layout: HomeLayout, id: string, size: WidgetSize): HomeLayout {
  if (!WIDGET_SIZES.includes(size)) return layout;
  return { ...layout, widgets: layout.widgets.map((w) => (w.id === id ? { ...w, size } : w)) };
}

export function removeWidget(layout: HomeLayout, id: string): HomeLayout {
  const w = layout.widgets.find((x) => x.id === id);
  if (!w || isLocked(w)) return layout;
  return { ...layout, widgets: layout.widgets.filter((x) => x.id !== id) };
}

export type NewWidget = Omit<WidgetInstance, 'id'>;

/** Stable identity of what a widget shows, so the gallery can say "already on Home". */
export function widgetKey(w: NewWidget): string {
  if (w.kind === 'app') return `app:${w.appId}/${w.widgetId}`;
  if (w.kind === 'system') return `system:${w.nodeId ?? '*'}`;
  return w.kind;
}

export function hasWidget(layout: HomeLayout, w: NewWidget): boolean {
  const k = widgetKey(w);
  return layout.widgets.some((x) => widgetKey(x) === k);
}

/** Add at the end. Refused (layout unchanged) when full or already present. */
export function addWidget(layout: HomeLayout, w: NewWidget): HomeLayout {
  if (layout.widgets.length >= MAX_WIDGETS || hasWidget(layout, w)) return layout;
  const base = widgetKey(w).replace(/[^a-z0-9]+/gi, '-');
  let id = `w-${base}`;
  for (let i = 2; layout.widgets.some((x) => x.id === id); i++) id = `w-${base}-${i}`;
  return { ...layout, widgets: [...layout.widgets, { ...w, id }] };
}

export function togglePin(layout: HomeLayout, appId: string): HomeLayout {
  if (layout.pinned.includes(appId)) return { ...layout, pinned: layout.pinned.filter((p) => p !== appId) };
  if (layout.pinned.length >= MAX_PINNED) return layout;
  return { ...layout, pinned: [...layout.pinned, appId] };
}

export function movePin(layout: HomeLayout, appId: string, to: number): HomeLayout {
  const from = layout.pinned.indexOf(appId);
  if (from < 0) return layout;
  const target = Math.max(0, Math.min(layout.pinned.length - 1, to));
  if (target === from) return layout;
  const next = layout.pinned.slice();
  next.splice(from, 1);
  next.splice(target, 0, appId);
  return { ...layout, pinned: next };
}

const KINDS: readonly WidgetKind[] = ['approvals', 'system', 'activity', 'backups', 'updates', 'mesh', 'app'];
const SAFE_ID = /^[a-z0-9][a-z0-9._:/*-]{0,80}$/i;

/**
 * Read a stored layout defensively: unknown kinds, bad sizes, duplicate ids and extras are
 * dropped; "Needs you" is restored to the first place. Anything unreadable gives the default.
 */
export function sanitizeLayout(raw: unknown): HomeLayout {
  if (!raw || typeof raw !== 'object' || (raw as { version?: unknown }).version !== 1) return DEFAULT_LAYOUT;
  const r = raw as { widgets?: unknown; pinned?: unknown };
  const seenIds = new Set<string>();
  const seenKeys = new Set<string>();
  const widgets: WidgetInstance[] = [];
  for (const x of Array.isArray(r.widgets) ? r.widgets : []) {
    if (!x || typeof x !== 'object') continue;
    const w = x as Record<string, unknown>;
    if (typeof w.id !== 'string' || !SAFE_ID.test(w.id) || seenIds.has(w.id)) continue;
    if (!KINDS.includes(w.kind as WidgetKind)) continue;
    const size = WIDGET_SIZES.includes(w.size as WidgetSize) ? (w.size as WidgetSize) : 'M';
    const inst: WidgetInstance = { id: w.id, kind: w.kind as WidgetKind, size };
    if (inst.kind === 'system' && typeof w.nodeId === 'string' && SAFE_ID.test(w.nodeId)) inst.nodeId = w.nodeId;
    if (inst.kind === 'app') {
      if (typeof w.appId !== 'string' || typeof w.widgetId !== 'string' || !SAFE_ID.test(w.appId) || !SAFE_ID.test(w.widgetId)) continue;
      inst.appId = w.appId;
      inst.widgetId = w.widgetId;
    }
    const k = widgetKey(inst);
    if (seenKeys.has(k)) continue;
    seenIds.add(inst.id);
    seenKeys.add(k);
    widgets.push(inst);
  }
  const locked = widgets.find(isLocked) ?? DEFAULT_LAYOUT.widgets[0]!;
  const rest = widgets.filter((w) => !isLocked(w)).slice(0, MAX_WIDGETS - 1);
  const pinned = Array.from(new Set((Array.isArray(r.pinned) ? r.pinned : []).filter((p): p is string => typeof p === 'string' && SAFE_ID.test(p)))).slice(0, MAX_PINNED);
  return { version: 1, widgets: [locked, ...rest], pinned };
}

/** Where a layout is kept. The dashboard backs this with the hub; the demo with the browser. */
export interface LayoutStore {
  load(personId: string): HomeLayout | null;
  save(personId: string, layout: HomeLayout): void;
}

/** Per-browser store (a convenience only, P4): survives reloads, never shared between devices. */
export function browserLayoutStore(storage: Pick<Storage, 'getItem' | 'setItem'> | undefined = globalThis.localStorage): LayoutStore {
  const key = (p: string) => `onemind.home.layout.v1:${p}`;
  return {
    load(personId) {
      try {
        const raw = storage?.getItem(key(personId));
        return raw ? sanitizeLayout(JSON.parse(raw)) : null;
      } catch {
        return null;
      }
    },
    save(personId, layout) {
      try {
        storage?.setItem(key(personId), JSON.stringify(layout));
      } catch {
        /* storage full or blocked: the layout still works for this visit */
      }
    },
  };
}

/** Installed apps in the dock, in pin order; pins for apps that are gone are skipped. */
export function dockApps(layout: HomeLayout, apps: HomeApp[]): HomeApp[] {
  const byId = new Map(apps.filter((a) => a.installed).map((a) => [a.id, a]));
  return layout.pinned.map((id) => byId.get(id)).filter((a): a is HomeApp => !!a);
}

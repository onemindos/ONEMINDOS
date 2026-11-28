// SPDX-License-Identifier: Apache-2.0
// Back to front is also least to most recently focused; geometry is a percentage of the usable stage.
export interface Rect { x: number; y: number; width: number; height: number }
/** `ws` is the workspace (0 to WORKSPACES - 1) the window lives on. */
export interface DesktopWindow { id: string; path: string; rect: Rect; minimised: boolean; maximised: boolean; ws: number }
export type Windows = DesktopWindow[];
export const LIMIT = 8;
/** Share of the stage width Home's tile column keeps free on the left when a window opens. */
export const HOME_COLUMN = 36;
export const WORKSPACES = 4;
export const validWorkspace = (n: unknown): n is number => Number.isInteger(n) && (n as number) >= 0 && (n as number) < WORKSPACES;

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));
export function fit(rect: Rect): Rect {
  const width = clamp(rect.width, 25, 100), height = clamp(rect.height, 20, 100);
  return { width, height, x: clamp(rect.x, 0, 100 - width), y: clamp(rect.y, 0, 100 - height) };
}

export const close = (windows: Windows, id: string) => windows.filter(w => w.id !== id);
export const minimise = (windows: Windows, id: string) => windows.map(w => w.id === id ? { ...w, minimised: true } : w);
export const toggleMax = (windows: Windows, id: string) => windows.map(w => w.id === id ? { ...w, maximised: !w.maximised } : w);
/** Placing a window (drag, keys, a snap layout) gives it that rectangle; a maximised window comes back down into it. */
export const position = (windows: Windows, id: string, rect: Rect) => windows.map(w => w.id === id ? { ...w, rect: fit(rect), maximised: false } : w);
/** The most recently focused open window, on one workspace when `ws` is given. */
export const top = (windows: Windows, ws?: number) => windows.filter(w => !w.minimised && (ws === undefined || w.ws === ws)).at(-1);
export const onWorkspace = (windows: Windows, ws: number) => windows.filter(w => w.ws === ws);
/** Send a window to another workspace; it stays minimised or open as it was. */
export const sendTo = (windows: Windows, id: string, ws: number) => validWorkspace(ws) ? windows.map(w => w.id === id ? { ...w, ws } : w) : windows;

/** Opening a screen puts it on `ws` (default: where it already is, else the first workspace). */
export function open(windows: Windows, id: string, path: string, ws?: number): Windows {
  const existing = windows.find(w => w.id === id);
  // New windows open right of Home's tile column (Atlas screen 01), cascading a little each time.
  const step = (windows.length % 5) * 2;
  const rect = { x: HOME_COLUMN + step, y: 2 + step, width: ['storage', 'backups'].includes(id) ? 40 : 100 - HOME_COLUMN - 10, height: 84 };
  return [...close(windows, id).slice(1 - LIMIT), { rect, maximised: false, ws: 0, ...existing, id, path, minimised: false, ...(ws === undefined ? {} : { ws }) }];
}
export function focus(windows: Windows, id: string): Windows {
  const existing = windows.find(w => w.id === id);
  return existing ? open(windows, id, existing.path) : windows;
}

export function save(windows: Windows): string {
  return JSON.stringify(windows.map(({ path, rect, minimised, maximised, ws }) => ({ path: path.split(/[?#]/)[0], rect, minimised, maximised, ws })));
}
export function restore(raw: string | null, screenFor: (path: string) => string | undefined): Windows {
  let windows: Windows = [];
  try {
    const items: unknown = JSON.parse(raw ?? '[]');
    if (!Array.isArray(items)) return [];
    for (const item of items) {
      if (typeof item?.path !== 'string' || !/^\/(?!\/)/.test(item.path) || /[?#\\\s]/.test(item.path)) continue;
      const id = screenFor(item.path);
      const rect = item.rect;
      if (!id || !rect || ![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite)) continue;
      windows = [...close(windows, id).slice(1 - LIMIT), { id, path: item.path, rect: fit(rect), minimised: item.minimised === true, maximised: item.maximised === true, ws: validWorkspace(item.ws) ? item.ws : 0 }];
    }
  } catch { /* Invalid or unavailable preferences start a fresh desktop. */ }
  return windows;
}

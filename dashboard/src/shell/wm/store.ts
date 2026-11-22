// SPDX-License-Identifier: Apache-2.0
// Back to front is also least to most recently focused; geometry is a percentage of the usable stage.
export interface Rect { x: number; y: number; width: number; height: number }
export interface DesktopWindow { id: string; path: string; rect: Rect; minimised: boolean; maximised: boolean }
export type Windows = DesktopWindow[];
export const LIMIT = 8;

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));
export function fit(rect: Rect): Rect {
  const width = clamp(rect.width, 25, 100), height = clamp(rect.height, 20, 100);
  return { width, height, x: clamp(rect.x, 0, 100 - width), y: clamp(rect.y, 0, 100 - height) };
}

export const close = (windows: Windows, id: string) => windows.filter(w => w.id !== id);
export const minimise = (windows: Windows, id: string) => windows.map(w => w.id === id ? { ...w, minimised: true } : w);
export const toggleMax = (windows: Windows, id: string) => windows.map(w => w.id === id ? { ...w, maximised: !w.maximised } : w);
export const position = (windows: Windows, id: string, rect: Rect) => windows.map(w => w.id === id ? { ...w, rect: fit(rect) } : w);
export const top = (windows: Windows) => windows.filter(w => !w.minimised).at(-1);

export function open(windows: Windows, id: string, path: string): Windows {
  const existing = windows.find(w => w.id === id);
  const offset = 3 + (windows.length % 5) * 3;
  const rect = { x: offset, y: offset, width: ['storage', 'backups'].includes(id) ? 60 : 82, height: 80 };
  return [...close(windows, id).slice(1 - LIMIT), { rect, maximised: false, ...existing, id, path, minimised: false }];
}
export function focus(windows: Windows, id: string): Windows {
  const existing = windows.find(w => w.id === id);
  return existing ? open(windows, id, existing.path) : windows;
}

export function save(windows: Windows): string {
  return JSON.stringify(windows.map(({ path, rect, minimised, maximised }) => ({ path: path.split(/[?#]/)[0], rect, minimised, maximised })));
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
      windows = [...close(windows, id).slice(1 - LIMIT), { id, path: item.path, rect: fit(rect), minimised: item.minimised === true, maximised: item.maximised === true }];
    }
  } catch { /* Invalid or unavailable preferences start a fresh desktop. */ }
  return windows;
}

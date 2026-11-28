// SPDX-License-Identifier: Apache-2.0
// Tiling geometry as pure functions: each layout fills the whole stage (100 x 100) with no overlap.
// Tiling is a view over the windows, so turning it off gives every window its own size back.
import type { Rect } from './store';

export const LAYOUTS = ['halves', 'thirds', 'quarters', 'main-stack'] as const;
export type Layout = typeof LAYOUTS[number];
export const LAYOUT_LABELS: Record<Layout, string> = { halves: 'Halves', thirds: 'Thirds', quarters: 'Quarters', 'main-stack': 'Main and stack' };
export const isLayout = (v: unknown): v is Layout => LAYOUTS.includes(v as Layout);

/** Equal columns (at most `max`), each holding its windows stacked; earlier columns take the extras. */
function columns(n: number, max: number): Rect[] {
  const cols = Math.min(n, max);
  const rects: Rect[] = [];
  for (let c = 0; c < cols; c++) {
    const count = Math.floor(n / cols) + (c < n % cols ? 1 : 0);
    for (let r = 0; r < count; r++) rects.push({ x: c * 100 / cols, y: r * 100 / count, width: 100 / cols, height: 100 / count });
  }
  return rects;
}

/** Two columns read row by row; an odd last window spans the full width of its row. */
function grid(n: number): Rect[] {
  if (n === 1) return [{ x: 0, y: 0, width: 100, height: 100 }];
  const rows = Math.ceil(n / 2);
  return Array.from({ length: n }, (_, i) => {
    const row = Math.floor(i / 2);
    const alone = i === n - 1 && n % 2 === 1;
    return { x: alone || i % 2 === 0 ? 0 : 50, y: row * 100 / rows, width: alone ? 100 : 50, height: 100 / rows };
  });
}

/** One large window on the left, the rest stacked on the right. */
function mainStack(n: number): Rect[] {
  if (n === 1) return [{ x: 0, y: 0, width: 100, height: 100 }];
  const rest = n - 1;
  return [{ x: 0, y: 0, width: 60, height: 100 }, ...Array.from({ length: rest }, (_, i) => ({ x: 60, y: i * 100 / rest, width: 40, height: 100 / rest }))];
}

/** The rectangle for each of `n` windows, in the order given (back to front focus order is the caller's). */
export function tile(layout: Layout, n: number): Rect[] {
  if (n < 1) return [];
  return { halves: () => columns(n, 2), thirds: () => columns(n, 3), quarters: () => grid(n), 'main-stack': () => mainStack(n) }[layout]();
}

/** Off, then each layout in turn, then off again. */
export const nextLayout = (current: Layout | null): Layout | null => current ? LAYOUTS[LAYOUTS.indexOf(current) + 1] ?? null : LAYOUTS[0];

/** Dragging a window until the pointer is within this share of the stage width snaps it to that half. */
export const SNAP_EDGE = 2;
/** The half a drag released at `xPercent` (of the stage width) snaps to, or null away from the edges. */
export function snapRect(xPercent: number): Rect | null {
  if (xPercent <= SNAP_EDGE) return { x: 0, y: 0, width: 50, height: 100 };
  if (xPercent >= 100 - SNAP_EDGE) return { x: 50, y: 0, width: 50, height: 100 };
  return null;
}

/** One place a window can snap to: `where` finishes "<window> …" ("on the right third"). */
export interface SnapZone { where: string; rect: Rect }
const third = 100 / 3;
const col = (x: number, width: number): Rect => ({ x, y: 0, width, height: 100 });
/** The snap layouts flyout on a window's maximise button (Atlas 01b): each layout's zones fill the stage width. */
export const SNAP_LAYOUTS: readonly { id: string; zones: SnapZone[] }[] = [
  { id: 'halves', zones: [{ where: 'on the left half', rect: col(0, 50) }, { where: 'on the right half', rect: col(50, 50) }] },
  { id: 'wide-left', zones: [{ where: 'on the left two thirds', rect: col(0, 2 * third) }, { where: 'on the right third', rect: col(2 * third, third) }] },
  { id: 'wide-right', zones: [{ where: 'on the left third', rect: col(0, third) }, { where: 'on the right two thirds', rect: col(third, 2 * third) }] },
  { id: 'thirds', zones: [{ where: 'on the left third', rect: col(0, third) }, { where: 'in the middle third', rect: col(third, third) }, { where: 'on the right third', rect: col(2 * third, third) }] },
];

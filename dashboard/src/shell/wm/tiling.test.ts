// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { LAYOUTS, SNAP_EDGE, nextLayout, snapRect, tile } from './tiling';
import { fit, type Rect } from './store';

const area = (r: Rect) => r.width * r.height;
const overlap = (a: Rect, b: Rect) => Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));

it.each(LAYOUTS)('%s fills the whole stage with no overlap for 1 to 8 windows', layout => {
  for (let n = 1; n <= 8; n++) {
    const rects = tile(layout, n);
    expect(rects).toHaveLength(n);
    expect(rects.reduce((sum, r) => sum + area(r), 0)).toBeCloseTo(10000, 6);
    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(0);
      expect(r.y).toBeGreaterThanOrEqual(0);
      expect(r.x + r.width).toBeLessThanOrEqual(100 + 1e-9);
      expect(r.y + r.height).toBeLessThanOrEqual(100 + 1e-9);
    }
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) expect(overlap(rects[i]!, rects[j]!)).toBeLessThan(1e-9);
  }
  expect(tile(layout, 0)).toEqual([]);
});

it('lays out halves, thirds, quarters and main-plus-stack as named', () => {
  expect(tile('halves', 2)).toEqual([{ x: 0, y: 0, width: 50, height: 100 }, { x: 50, y: 0, width: 50, height: 100 }]);
  expect(tile('thirds', 3).map(r => r.width)).toEqual([100 / 3, 100 / 3, 100 / 3]);
  expect(tile('quarters', 4).map(r => [r.x, r.y, r.width, r.height])).toEqual([[0, 0, 50, 50], [50, 0, 50, 50], [0, 50, 50, 50], [50, 50, 50, 50]]);
  expect(tile('main-stack', 3)).toEqual([{ x: 0, y: 0, width: 60, height: 100 }, { x: 60, y: 0, width: 40, height: 50 }, { x: 60, y: 50, width: 40, height: 50 }]);
  expect(tile('main-stack', 1)).toEqual([{ x: 0, y: 0, width: 100, height: 100 }]);
});

it('steps from off through every layout and back to off', () => {
  expect([nextLayout(null), nextLayout('halves'), nextLayout('thirds'), nextLayout('quarters'), nextLayout('main-stack')]).toEqual(['halves', 'thirds', 'quarters', 'main-stack', null]);
});

it('snaps a drag released at the left or right edge to that half, and nowhere else', () => {
  expect(snapRect(0)).toEqual({ x: 0, y: 0, width: 50, height: 100 });
  expect(snapRect(100)).toEqual({ x: 50, y: 0, width: 50, height: 100 });
  expect(snapRect(SNAP_EDGE + 0.1)).toBeNull();
  expect(snapRect(50)).toBeNull();
  expect(fit(snapRect(0)!)).toEqual(snapRect(0));
});

// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { close, focus, minimise, open, position, restore, save, toggleMax, type Windows } from './store';

it('focus orders windows and the ninth distinct screen evicts the least recently focused', () => {
  let windows: Windows = [];
  for (let i = 0; i < 8; i++) windows = open(windows, String(i), '/' + i);
  windows = focus(windows, '0');
  expect(open(windows, '8', '/8').map(w => w.id)).toEqual(['2', '3', '4', '5', '6', '7', '0', '8']);
  expect(open(windows, '0', '/0/detail')).toHaveLength(8);
});

it('restores geometry after maximise, minimises to the dock and focuses from it', () => {
  const rect = { x: 3, y: 6, width: 60, height: 75 };
  let windows = position(open([], 'market', '/market'), 'market', rect);
  windows = toggleMax(windows, 'market');
  expect(windows[0]?.maximised).toBe(true);
  expect(toggleMax(windows, 'market')[0]?.rect).toEqual(rect);
  expect(minimise(windows, 'market')[0]?.minimised).toBe(true);
  expect(focus(minimise(windows, 'market'), 'market')[0]?.minimised).toBe(false);
  expect(close(windows, 'market')).toEqual([]);
});

it('restores only valid screens, geometry and pathnames, in saved order', () => {
  const windows = open(open([], 'removed', '/gone'), 'market', '/market?q=private#fragment');
  const data = save(windows);
  expect(data).not.toContain('private');
  expect(restore(data, path => path === '/market' ? 'market' : undefined)).toEqual(open([], 'market', '/market').map(w => ({ ...w, rect: windows[1]!.rect })));
  expect(restore('invalid', () => 'market')).toEqual([]);
});

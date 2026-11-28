// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { HOME_COLUMN, close, focus, minimise, onWorkspace, open, position, restore, save, sendTo, toggleMax, top, type Windows } from './store';

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

it('keeps each workspace’s windows apart, moves a window between them and saves the workspace', () => {
  let windows: Windows = open(open([], 'market', '/market', 0), 'nodes', '/nodes', 1);
  expect(onWorkspace(windows, 0).map(w => w.id)).toEqual(['market']);
  expect(onWorkspace(windows, 1).map(w => w.id)).toEqual(['nodes']);
  expect(top(windows, 0)?.id).toBe('market');
  expect(top(windows, 2)).toBeUndefined();
  expect(focus(windows, 'market').find(w => w.id === 'market')?.ws).toBe(0);
  windows = sendTo(windows, 'market', 3);
  expect(onWorkspace(windows, 3).map(w => w.id)).toEqual(['market']);
  expect(sendTo(windows, 'market', 4)).toBe(windows);
  const back = restore(save(windows), path => path.slice(1));
  expect(back.map(w => [w.id, w.ws])).toEqual([['market', 3], ['nodes', 1]]);
  expect(restore(JSON.stringify([{ path: '/market', rect: windows[0]!.rect, ws: 9 }]), path => path.slice(1))[0]?.ws).toBe(0);
});

it('opens new windows right of Home’s tile column and inside the stage, cascading', () => {
  let windows: Windows = [];
  for (let i = 0; i < 6; i++) windows = open(windows, String(i), '/' + i);
  for (const { rect } of [...windows, ...open([], 'backups', '/backups')]) {
    expect(rect.x).toBeGreaterThanOrEqual(HOME_COLUMN);
    expect(rect.x + rect.width).toBeLessThanOrEqual(100);
    expect(rect.y + rect.height).toBeLessThanOrEqual(100);
  }
  expect(new Set(windows.map(w => w.rect.x)).size).toBeGreaterThan(1);
});

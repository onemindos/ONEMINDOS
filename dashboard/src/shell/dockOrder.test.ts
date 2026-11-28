// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { dockOrder, dockSplit } from './dock';
import { orderDock } from './dockOrder';

const shipped = ['home', 'market', 'installed', 'approvals'];

it('keeps the shipped order with no preference', () => {
  expect(orderDock(shipped, undefined)).toEqual(shipped);
  expect(orderDock(shipped, [])).toEqual(shipped);
});

it('puts the saved order first, ignores unknown ids and keeps unnamed screens in their shipped place after it', () => {
  expect(orderDock(shipped, ['approvals', 'gone', 'home', 'approvals'])).toEqual(['approvals', 'home', 'market', 'installed']);
});

const nav = () => dockOrder().map((id) => ({ id, label: id, href: `/${id}`, icon: 'home' }) as never);

it('an empty preference keeps the full default dock, Map included', () => {
  const dock = dockSplit(nav(), orderDock(dockOrder(), [])).dock.map((n) => n.id);
  expect(dock).toEqual(dockSplit(nav()).dock.map((n) => n.id));
  expect(dock).toEqual(dockOrder());
});

it('a saved order that names one screen keeps every other dock screen', () => {
  const last = dockOrder().at(-1)!;
  const dock = dockSplit(nav(), orderDock(dockOrder(), [last])).dock.map((n) => n.id);
  expect(dock[0]).toBe(last);
  expect([...dock].sort()).toEqual([...dockOrder()].sort());
});

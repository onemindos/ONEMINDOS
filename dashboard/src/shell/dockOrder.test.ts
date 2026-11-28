// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { dockSplit } from './DesktopShell';
import { orderDock } from './dockOrder';

const shipped = ['home', 'market', 'installed', 'approvals'];

it('keeps the shipped order with no preference', () => {
  expect(orderDock(shipped, undefined)).toEqual(shipped);
  expect(orderDock(shipped, [])).toEqual(shipped);
});

it('puts the saved order first, ignores unknown ids and keeps unnamed screens in their shipped place after it', () => {
  expect(orderDock(shipped, ['approvals', 'gone', 'home', 'approvals'])).toEqual(['approvals', 'home', 'market', 'installed']);
});

it('the dock follows the saved order', () => {
  const nav = shipped.map((id) => ({ id, label: id, href: `/${id}`, icon: 'home' }) as never);
  expect(dockSplit(nav, ['approvals']).dock.map((n) => n.id)[0]).toBe('approvals');
});

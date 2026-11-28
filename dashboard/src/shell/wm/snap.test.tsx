// SPDX-License-Identifier: Apache-2.0
// Snap layouts (Atlas 01b): the flyout on the maximise button, and Alt Shift ← / → for the halves.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderApp } from '../../test/helpers';
import { position, open as openWindow } from './store';
import { SNAP_LAYOUTS } from './tiling';

beforeEach(() => {
  if (!window.localStorage) {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => values.set(k, v), removeItem: (k: string) => values.delete(k) });
  }
});

const frame = (id: string) => document.querySelector<HTMLElement>(`[data-window-id="${id}"]`)!;

it('every snap layout fills the stage width once, left to right, without overlap', () => {
  for (const { zones } of SNAP_LAYOUTS) {
    let x = 0;
    for (const { rect } of zones) {
      expect(rect.x).toBeCloseTo(x);
      expect([rect.y, rect.height]).toEqual([0, 100]);
      x += rect.width;
    }
    expect(x).toBeCloseTo(100);
  }
});

it('placing a maximised window brings it down into the new rectangle', () => {
  const max = openWindow([], 'market', '/market').map((w) => ({ ...w, maximised: true }));
  expect(position(max, 'market', { x: 50, y: 0, width: 50, height: 100 })[0]).toMatchObject({ maximised: false, rect: { x: 50, width: 50 } });
});

it('hovering maximise opens the snap layouts; a zone snaps the window there and closes the flyout', async () => {
  const user = userEvent.setup();
  const { container } = renderApp({ token: 'owner-demo', route: '/market' });
  const win = await screen.findByRole('region', { name: 'Market' });
  await user.hover(within(win).getByRole('button', { name: 'Maximise Market' }));
  const flyout = await screen.findByRole('group', { name: 'Snap Market' });
  expect(within(win).getByRole('button', { name: 'Maximise Market' })).toHaveAttribute('aria-expanded', 'true');
  const a11y = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
  expect(a11y.violations.map((v) => v.id)).toEqual([]);
  await user.click(within(flyout).getAllByRole('button', { name: 'Market on the right third' })[0]!);
  expect(parseFloat(frame('market').style.left)).toBeCloseTo(200 / 3);
  expect(parseFloat(frame('market').style.width)).toBeCloseTo(100 / 3);
  expect(screen.queryByRole('group', { name: 'Snap Market' })).toBeNull();
});

it('opens from the keyboard with the down arrow, focuses the first zone, and Esc closes only the flyout', async () => {
  const user = userEvent.setup();
  renderApp({ token: 'owner-demo', route: '/market' });
  const win = await screen.findByRole('region', { name: 'Market' });
  const max = within(win).getByRole('button', { name: 'Maximise Market' });
  max.focus();
  await user.keyboard('{ArrowDown}');
  expect(await screen.findByRole('button', { name: 'Market on the left half' })).toHaveFocus();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('group', { name: 'Snap Market' })).toBeNull());
  expect(max).toHaveFocus();
  expect(screen.getByRole('region', { name: 'Market' })).toBeInTheDocument();
});

it('Esc closes a hover-opened flyout and leaves the window open', async () => {
  const user = userEvent.setup();
  renderApp({ token: 'owner-demo', route: '/market' });
  const win = await screen.findByRole('region', { name: 'Market' });
  await user.hover(within(win).getByRole('button', { name: 'Maximise Market' }));
  await screen.findByRole('group', { name: 'Snap Market' });
  fireEvent.keyDown(window, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('group', { name: 'Snap Market' })).toBeNull());
  expect(screen.getByRole('region', { name: 'Market' })).toBeInTheDocument();
  // With the flyout closed, Esc closes the window as before.
  fireEvent.keyDown(window, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Market' })).toBeNull());
});

it('Alt Shift ← and → snap the focused window to a half, also out of maximised', async () => {
  const user = userEvent.setup();
  renderApp({ token: 'owner-demo', route: '/market' });
  const win = await screen.findByRole('region', { name: 'Market' });
  await user.click(within(win).getByRole('button', { name: 'Maximise Market' }));
  expect(frame('market').style.width).toBe('100%');
  fireEvent.keyDown(window, { key: 'ArrowLeft', code: 'ArrowLeft', altKey: true, shiftKey: true });
  await waitFor(() => expect(frame('market').style.width).toBe('50%'));
  expect(frame('market').style.left).toBe('0%');
  fireEvent.keyDown(window, { key: 'ArrowRight', code: 'ArrowRight', altKey: true, shiftKey: true });
  await waitFor(() => expect(frame('market').style.left).toBe('50%'));
});

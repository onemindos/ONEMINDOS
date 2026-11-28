// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { BrowserRouter } from 'react-router';
import { App } from '../../App';
import { SessionProvider } from '../../session';
import { MockApi } from '../../api/mock';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { openScreen, renderApp } from '../../test/helpers';
import { personStorage } from '../../data/prefs';
import { HOME_COLUMN } from './store';

beforeEach(() => {
  if (!window.localStorage) {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
  }
});
afterEach(() => vi.unstubAllGlobals());

it('keeps both routes mounted, restores their geometry, and closes only the focused window', async () => {
  const user = userEvent.setup();
  const first = renderApp({ token: 'owner-demo', route: '/approvals' });
  const approvals = await screen.findByRole('region', { name: 'Approvals' });
  await openScreen(user, /Market/);
  const market = await screen.findByRole('region', { name: 'Market' });
  expect(approvals).toBeInTheDocument();
  const mover = within(market).getByRole('button', { name: 'Move Market' });
  const before = market.style.left;
  fireEvent.keyDown(mover, { key: 'ArrowRight' });
  const left = market.style.left;
  expect(left).not.toBe(before);
  const a11y = await axe.run(first.container, { rules: { 'color-contrast': { enabled: false } } });
  expect(a11y.violations.map(v => v.id)).toEqual([]);
  const stored = JSON.parse(personStorage('owner')!.getItem('shell.windows')!);
  expect(stored.map((w: { path: string }) => w.path)).toEqual(['/approvals', '/market']);
  expect(stored.every((w: { minimised: boolean }) => !w.minimised)).toBe(true);
  first.unmount();
  renderApp({ token: 'owner-demo' });
  const again = await screen.findByRole('region', { name: 'Market' });
  expect(again.style.left).toBe(left);
  expect(screen.getByRole('region', { name: 'Approvals' })).toBeInTheDocument();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Market' })).toBeNull());
  expect(screen.getByRole('region', { name: 'Approvals' })).toBeInTheDocument();
});

it('drops unknown and restricted screens from a simple person’s saved session', async () => {
  const rect = { x: 0, y: 0, width: 80, height: 80 };
  personStorage('sam')!.setItem('shell.windows', JSON.stringify(['/gone', '/sources', '/settings/users', '/settings/removed', '/nodes', '/market'].map(path => ({ path, rect }))));
  renderApp({ token: 'guest-demo' });
  await screen.findByRole('region', { name: 'Market' });
  expect(screen.queryByRole('region', { name: 'Nodes' })).toBeNull();
  expect(personStorage('sam')!.getItem('shell.windows')).not.toMatch(/gone|sources|settings|nodes/);
});

it('restores just the top screen on a narrow display', async () => {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(max-width: 720px)', addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  const rect = { x: 4, y: 4, width: 80, height: 80 };
  personStorage('owner')!.setItem('shell.windows', JSON.stringify(['/approvals', '/market', '/nodes'].map(path => ({ path, rect, minimised: path === '/nodes' }))));
  renderApp({ token: 'owner-demo' });
  await screen.findByRole('region', { name: 'Market' });
  expect(screen.queryByRole('region', { name: 'Approvals' })).toBeNull();
});

it('follows browser history and restores the same owner under a newly issued token', async () => {
  const user = userEvent.setup();
  const deps = { mock: false, knownPrincipal: () => undefined, makeApi: () => new MockApi('owner-demo') };
  const visit = (token: string, path: string) => {
    sessionStorage.setItem('onemind.token', token);
    history.replaceState(null, '', path);
    return render(<BrowserRouter><SessionProvider deps={deps}><App mock={false} /></SessionProvider></BrowserRouter>);
  };
  const first = visit('first-test-session', '/approvals?highlight=test');
  await screen.findByRole('region', { name: 'Approvals' });
  await openScreen(user, /Market/);
  expect(location.pathname).toBe('/market');
  act(() => history.back());
  await waitFor(() => expect(location.pathname).toBe('/approvals'));
  await waitFor(() => expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: /Approvals/ })).toHaveAttribute('aria-current', 'page'));
  act(() => history.forward());
  await waitFor(() => expect(location.pathname).toBe('/market'));
  await user.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: /Market/ }));
  first.unmount();
  visit('renewed-test-session', '/');
  await screen.findByRole('region', { name: 'Market' });
  expect(location.pathname).toBe('/market');
  expect(screen.getByRole('region', { name: 'Approvals' })).toBeInTheDocument();
  expect(personStorage('owner')!.getItem('shell.windows')).not.toContain('highlight');
});

const frame = (id: string) => document.querySelector<HTMLElement>(`[data-window-id="${id}"]`)!;

it('switches workspaces from the menu bar and Alt+digit, keeping each set of windows, and remembers tiling', async () => {
  const user = userEvent.setup();
  renderApp({ token: 'owner-demo', route: '/approvals' });
  await screen.findByRole('region', { name: 'Approvals' });
  const spaces = screen.getByRole('group', { name: 'Workspaces' });
  expect(within(spaces).getAllByRole('button')).toHaveLength(4);
  await user.click(within(spaces).getByRole('button', { name: 'Workspace 2' }));
  expect(within(spaces).getByRole('button', { name: 'Workspace 2' })).toHaveAttribute('aria-pressed', 'true');
  expect(frame('approvals').hidden).toBe(true);
  await openScreen(user, /Market/);
  await waitFor(() => expect(frame('market').hidden).toBe(false));
  const market = frame('market');
  expect(market.hidden).toBe(false);
  fireEvent.keyDown(window, { key: '¡', code: 'Digit1', altKey: true });
  await waitFor(() => expect(frame('approvals').hidden).toBe(false));
  expect(frame('market').hidden).toBe(true);
  // Send the window to workspace 3 with Alt+Shift+3: it leaves this workspace.
  fireEvent.keyDown(window, { key: '£', code: 'Digit3', altKey: true, shiftKey: true });
  await waitFor(() => expect(frame('approvals').hidden).toBe(true));
  fireEvent.keyDown(window, { key: '£', code: 'Digit3', altKey: true });
  await waitFor(() => expect(frame('approvals').hidden).toBe(false));
  const stored = JSON.parse(personStorage('owner')!.getItem('shell.windows')!);
  expect(stored.map((w: { ws: number }) => w.ws).sort()).toEqual([1, 2]);
  expect(personStorage('owner')!.getItem('shell.workspace')).toBe('2');
  await user.click(screen.getByRole('button', { name: /^Tiling: off/ }));
  expect(personStorage('owner')!.getItem('shell.tiling')).toBe('halves');
});

it('tiles the open windows of the workspace only while tiling is on, and the shortcuts sheet opens with ?', async () => {
  const user = userEvent.setup();
  personStorage('owner')!.setItem('shell.tiling', 'halves');
  const rect = { x: 3, y: 3, width: 60, height: 60 };
  personStorage('owner')!.setItem('shell.windows', JSON.stringify(['/approvals', '/market'].map(path => ({ path, rect }))));
  renderApp({ token: 'owner-demo' });
  const market = await screen.findByRole('region', { name: 'Market' });
  const approvals = frame('approvals');
  expect([approvals.style.width, market.style.width]).toEqual(['50%', '50%']);
  expect(new Set([approvals.style.left, market.style.left])).toEqual(new Set(['0%', '50%']));
  for (let i = 0; i < 4; i++) await user.click(screen.getByRole('button', { name: /^Tiling: / }));
  expect(screen.getByRole('button', { name: /^Tiling: off/ })).toBeInTheDocument();
  expect(market.style.width).toBe('60%');
  (document.activeElement as HTMLElement).blur();
  await user.keyboard('?');
  expect(await screen.findByRole('dialog', { name: 'Keyboard shortcuts' })).toBeInTheDocument();
});

it('visiting an empty workspace and back keeps both windows of workspace 1 open', async () => {
  const user = userEvent.setup();
  renderApp({ token: 'owner-demo', route: '/approvals' });
  await screen.findByRole('region', { name: 'Approvals' });
  await openScreen(user, /Market/);
  await waitFor(() => expect(frame('market').hidden).toBe(false));
  expect(frame('approvals').hidden).toBe(false);
  const spaces = screen.getByRole('group', { name: 'Workspaces' });
  await user.click(within(spaces).getByRole('button', { name: 'Workspace 2' }));
  await waitFor(() => expect(frame('market').hidden).toBe(true));
  await user.click(within(spaces).getByRole('button', { name: /^Workspace 1/ }));
  await waitFor(() => expect(frame('market').hidden).toBe(false));
  expect(frame('approvals').hidden).toBe(false);
});

it('opens a window over the desktop: Home stays painted behind it, inert, and the bare stage brings the desktop back with the window still open', async () => {
  const user = userEvent.setup();
  const { container } = renderApp({ token: 'owner-demo' });
  await screen.findByRole('heading', { level: 1, name: /^Good/ });
  await openScreen(user, /Market/);
  const market = await screen.findByRole('region', { name: 'Market' });
  // Right of Home's tile column (Atlas 01), not over it.
  expect(Number.parseFloat(market.style.left)).toBeGreaterThanOrEqual(HOME_COLUMN);
  const desktop = container.querySelector<HTMLElement>('.dsk-desktop')!;
  expect(desktop).toHaveAttribute('inert');
  expect(desktop).toHaveAttribute('aria-hidden', 'true');
  expect(desktop.textContent).toMatch(/Good (morning|afternoon|evening|night)/);
  expect(screen.queryByRole('heading', { level: 1, name: /^Good/ })).toBeNull();
  // A click on the bare wallpaper focuses the desktop; the window stays where it was, no longer active.
  fireEvent.pointerDown(container.querySelector('.wm-stage')!);
  expect(await screen.findByRole('heading', { level: 1, name: /^Good/ })).toBe(desktop.querySelector('h1'));
  expect(desktop).not.toHaveAttribute('inert');
  expect(frame('market').hidden).toBe(false);
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: /Home/ })).toHaveAttribute('aria-current', 'page');
  // Clicking the window gives it focus again.
  fireEvent.pointerDown(frame('market'));
  await waitFor(() => expect(desktop).toHaveAttribute('inert'));
});

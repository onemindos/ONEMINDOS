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

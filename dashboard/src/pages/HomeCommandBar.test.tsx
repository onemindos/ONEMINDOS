// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { renderApp } from '../test/helpers';
import { preferenceStores } from '../data/prefs';
import { HomeCommandBar } from './HomeCommandBar';

it('opens the command palette and only offers chat for an installed agent with a launch URL', () => {
  const open = vi.fn();
  const { rerender } = render(<HomeCommandBar apps={[]} openPalette={open} />);
  expect(screen.queryByRole('link')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Run a command' }));
  expect(open).toHaveBeenCalledOnce();
  const agent = { id: 'hermes-agent', installed: true, web_port: 9119 };
  const loc = { hostname: 'hub.local', protocol: 'https:' };
  rerender(<HomeCommandBar apps={[agent]} openPalette={open} location={loc} />);
  expect(screen.getByRole('link', { name: /Ask an agent/ })).toHaveAttribute('href', 'https://hermes-agent.hub.local/');
  rerender(<HomeCommandBar apps={[{ ...agent, installed: false }]} openPalette={open} location={loc} />);
  expect(screen.queryByRole('link')).toBeNull();
});

it('restores the Home command bar from the signed-in person’s appearance choice', async () => {
  const appearance = renderApp({ token: 'owner-demo', route: '/settings/appearance' });
  const toggle = await screen.findByRole('checkbox', { name: 'Show the Home command bar' });
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  const { store } = preferenceStores('owner', { token: 'owner-demo' });
  await waitFor(async () => expect((await store.load()).prefs.commandBar).toBe(true));
  appearance.unmount();
  renderApp({ token: 'owner-demo', route: '/' });
  // The desktop restores the open Settings window across sessions. Close it to return Home.
  fireEvent.click(await screen.findByRole('button', { name: 'Close Settings' }));
  expect(await screen.findByRole('group', { name: 'Home commands' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Run a command' }));
  expect(await screen.findByRole('combobox')).toBeVisible();
});

it('keeps search one click away on the desktop while the command bar is off', async () => {
  renderApp({ token: 'owner-demo', route: '/' });
  // The Atlas desktop Home has no search field of its own: search lives in the menu bar.
  await screen.findByRole('heading', { level: 1, name: /^Good/ });
  expect(screen.queryByRole('button', { name: /Search apps, nodes and settings/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Search (Ctrl K)' })).toBeVisible();
  expect(screen.queryByRole('group', { name: 'Home commands' })).toBeNull();
});

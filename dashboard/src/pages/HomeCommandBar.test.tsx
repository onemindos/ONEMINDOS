// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

it('restores the run bar from the signed-in person’s appearance choice: in the dock on the desktop (final design 09)', async () => {
  const appearance = renderApp({ token: 'owner-demo', route: '/settings/appearance' });
  const toggle = await screen.findByRole('switch', { name: 'Show the run bar (Alt R)' });
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  const { store } = preferenceStores('owner', { token: 'owner-demo' });
  await waitFor(async () => expect((await store.load()).prefs.commandBar).toBe(true));
  appearance.unmount();
  renderApp({ token: 'owner-demo', route: '/' });
  // The desktop restores the open Settings window across sessions. Close it to return Home.
  fireEvent.click(await screen.findByRole('button', { name: 'Close Settings' }));
  // On the desktop the bar lives in the dock, not on Home (no second copy of it).
  const bar = await screen.findByRole('search', { name: 'Run bar' });
  expect(screen.queryByRole('group', { name: 'Home commands' })).toBeNull();
  const input = within(bar).getByRole('textbox', { name: 'Run a command or ask an agent' });
  fireEvent.change(input, { target: { value: 'nodes' } });
  fireEvent.submit(bar);
  expect(await screen.findByRole('region', { name: 'Nodes' })).toBeInTheDocument();
  // The Console view (sidebar) has no dock: there the bar stays on Home and opens the palette.
  fireEvent.click(screen.getByRole('button', { name: /Account/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Console view' }));
  fireEvent.click((await screen.findAllByRole('link', { name: /^Home$/ }))[0]!);
  expect(await screen.findByRole('group', { name: 'Home commands' })).toBeVisible();
  expect(screen.queryByRole('search', { name: 'Run bar' })).toBeNull();
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
  expect(screen.queryByRole('search', { name: 'Run bar' })).toBeNull(); // off by default (#501)
});

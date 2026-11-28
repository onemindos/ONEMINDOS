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
  const toggle = await screen.findByRole('switch', { name: 'Show the run bar (Alt R)' });
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

it('keeps the Search button on Pro Home while the command bar is off', async () => {
  renderApp({ token: 'owner-demo', route: '/' });
  expect(await screen.findByRole('button', { name: /Search apps, nodes and settings/ })).toBeVisible();
  expect(screen.queryByRole('group', { name: 'Home commands' })).toBeNull();
});

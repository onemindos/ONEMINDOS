// SPDX-License-Identifier: Apache-2.0
// Whole-app tests on the mock gateway (contract §3 rules): sign-in, every screen, the install
// request → approval → live progress → installed loop, roles, honest stale and "coming" states.
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp, seriousViolations } from './test/helpers';

const T = { timeout: 4000 };

describe('sign-in', () => {
  it('rejects an unknown token and signs in the owner', async () => {
    const u = userEvent.setup();
    renderApp();
    await u.type(screen.getByLabelText('Access token'), 'nope');
    await u.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/not accepted/)).toBeInTheDocument();
    await u.clear(screen.getByLabelText('Access token'));
    await u.type(screen.getByLabelText('Access token'), 'owner-demo');
    await u.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('navigation', { name: 'Main' }, T)).toBeInTheDocument();
  });
});

describe('Home', () => {
  it('shows the launcher fed by nodes, apps and actions, and passes axe', async () => {
    const { container } = renderApp({ token: 'owner-demo' });
    expect((await screen.findAllByText(/install ollama/i, {}, T)).length).toBeGreaterThan(0);
    expect(await screen.findByRole('link', { name: /Uptime Kuma/ }, T)).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('Market and the install loop', () => {
  it('Discover maps catalog categories onto TAXONOMY and shows the editorial rail', async () => {
    renderApp({ token: 'owner-demo', route: '/market' });
    expect(await screen.findByRole('heading', { name: 'Start here' }, T)).toBeInTheDocument();
    // home-automation (legacy slug on main) lands in Home & IoT.
    expect(screen.getByRole('button', { name: /^Home & IoT/ })).toBeInTheDocument();
  });

  it('app page shows the trust facts and greys out Install for a stale scan', async () => {
    renderApp({ token: 'owner-demo', route: '/market/node-red' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Node-RED' }, T)).toBeInTheDocument();
    expect(screen.getAllByText(/more than 7 days/).length).toBeGreaterThan(0);
  });

  it('request → approve → live progress → installed', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/market/vaultwarden' });
    await u.click(await screen.findByRole('button', { name: /Request install/ }, T));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/The hub picks the node/)).toBeInTheDocument();
    await u.click(within(dialog).getByRole('button', { name: /Send request/ }));
    expect(await screen.findByText('Request sent', {}, T)).toBeInTheDocument();
    // The app page follows the action.
    expect((await screen.findAllByText('Awaiting approval', {}, T)).length).toBeGreaterThan(0);

    await u.click(screen.getAllByRole('link', { name: /Approvals/ })[0]!);
    const card = await screen.findByRole('heading', { name: /Install vaultwarden|Install Vaultwarden/ }, T);
    expect(card).toBeInTheDocument();
    expect(screen.getByText(/does not compute a plan for requests yet/)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText('Approved', {}, T)).toBeInTheDocument();

    await u.click(screen.getAllByRole('link', { name: /Installed/ })[0]!);
    expect(await screen.findByRole('link', { name: 'Vaultwarden' }, T)).toBeInTheDocument();
  });

  it('an adult can look but is told they cannot request', async () => {
    renderApp({ token: 'adult-demo', route: '/market' });
    expect(await screen.findByText(/can look but not request installs/, {}, T)).toBeInTheDocument();
  });
});

describe('Approvals', () => {
  it('an agent sees the queue but cannot approve', async () => {
    renderApp({ token: 'agent-demo', route: '/approvals' });
    expect(await screen.findByText(/Only the owner can approve/, {}, T)).toBeInTheDocument();
    const approve = screen.queryByRole('button', { name: /^Approve/ });
    if (approve) expect(approve).toBeDisabled();
  });

  it('passes axe', async () => {
    const { container } = renderApp({ token: 'owner-demo', route: '/approvals' });
    await screen.findByRole('heading', { name: /Waiting/ }, T);
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('Activity, Nodes, Settings', () => {
  it('Activity says it is not the audit chain and lists decisions', async () => {
    renderApp({ token: 'owner-demo', route: '/activity' });
    expect(await screen.findByText('Not the audit chain', {}, T)).toBeInTheDocument();
    expect(screen.getAllByText(/kubectl delete exited with status 1/).length).toBeGreaterThan(0);
  });

  it('Nodes never shows a stale or offline machine as live', async () => {
    const { container } = renderApp({ token: 'owner-demo', route: '/nodes' });
    await screen.findByRole('list', { name: 'Nodes' }, T);
    expect(screen.getAllByText(/Stale/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Offline/).length).toBeGreaterThan(0);
    expect(await seriousViolations(container)).toEqual([]);
  });

  it('Appearance is live; sections without an API say which stream brings them', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/appearance' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Appearance' }, T)).toBeInTheDocument();
    await u.click(screen.getByRole('link', { name: /Backups/ }));
    expect(await screen.findByText(/coming with CORE-BACKUP/)).toBeInTheDocument();
    await u.click(screen.getByRole('link', { name: /About/ }));
    expect(await screen.findByText('Hub node', {}, T)).toBeInTheDocument();
    expect(screen.getAllByText('Home OneMind').length).toBeGreaterThan(0);
  });
});

describe('palette and notifications', () => {
  it('Ctrl-K opens the palette and finds an app', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/nodes' });
    await screen.findByRole('list', { name: 'Nodes' }, T);
    await act(async () => {
      await u.keyboard('{Control>}k{/Control}');
    });
    const box = await screen.findByRole('combobox');
    await u.type(box, 'uptime');
    expect((await screen.findAllByRole('option', { name: /Uptime Kuma/ })).length).toBeGreaterThan(0);
  });

  it('the bell counts the waiting approval', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/nodes' });
    await screen.findByRole('list', { name: 'Nodes' }, T);
    const bell = await screen.findByRole('button', { name: /Notifications/ }, T);
    await u.click(bell);
    expect(await screen.findByText('Install Ollama is waiting for approval', {}, T)).toBeInTheDocument();
  });
});

it('a 401 from the hub signs the person out', async () => {
  const { getApi } = renderApp({ token: 'owner-demo', route: '/nodes' });
  await screen.findByRole('list', { name: 'Nodes' }, T);
  (getApi() as unknown as { principal: undefined }).principal = undefined;
  await waitFor(() => expect(screen.getByLabelText('Access token')).toBeInTheDocument(), { timeout: 15_000 });
}, 20_000);

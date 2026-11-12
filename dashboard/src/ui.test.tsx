import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp, seriousViolations } from './test/helpers';

describe('sign-in', () => {
  it('rejects a bad token, then accepts a good one', async () => {
    renderApp();
    const user = userEvent.setup();
    const field = screen.getByLabelText('Access token');
    await user.type(field, 'wrong');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not accepted');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    await user.clear(field);
    await user.type(field, 'owner-demo');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument();
  });

  it('signs in and lands on Home', async () => {
    renderApp();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Access token'), 'owner-demo');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Home OneMind' })).toBeInTheDocument();
  });

  it('has no serious or critical axe violations', async () => {
    renderApp();
    expect(await seriousViolations()).toEqual([]);
  });
});

describe('Home', () => {
  it('shows node counts by status and installed apps', async () => {
    renderApp({ token: 'owner-demo' });
    const machines = await screen.findByRole('region', { name: 'Machines' });
    await waitFor(() => expect(within(machines).getAllByRole('listitem')).toHaveLength(3));
    const items = within(machines).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('2Online');
    expect(items[1]).toHaveTextContent('1Stale');
    expect(items[2]).toHaveTextContent('1Offline');
    const apps = screen.getByRole('region', { name: 'Your apps' });
    expect(await within(apps).findByRole('link', { name: /Uptime Kuma/ })).toBeInTheDocument();
    expect(within(apps).queryByText('Jellyfin')).toBeNull();
    expect(await seriousViolations()).toEqual([]);
  });
});

describe('Nodes', () => {
  it('shows a card per node with status badge and last seen, and never labels stale data as live', async () => {
    renderApp({ token: 'owner-demo', route: '/nodes' });
    const orin = await screen.findByRole('article', { name: 'orin-lab' });
    expect(within(orin).getByText('Stale')).toBeInTheDocument();
    expect(within(orin).getByText(/^5\ds ago$/)).toBeInTheDocument();
    expect(within(orin).getByText(/not live/)).toBeInTheDocument();
    expect(within(orin).getByText('NVIDIA Jetson Orin · Node')).toBeInTheDocument();

    const cloud = screen.getByRole('article', { name: 'cloud-1' });
    expect(within(cloud).getByText('Offline')).toBeInTheDocument();
    expect(within(cloud).getByText('14m ago')).toBeInTheDocument();
    expect(within(cloud).getByText('DigitalOcean droplet · Node')).toBeInTheDocument();

    const hub = screen.getByRole('article', { name: 'hub' });
    expect(within(hub).getByText('Online')).toBeInTheDocument();
    expect(within(hub).queryByText(/not live/)).toBeNull();
    expect(within(hub).getByText('server · ready')).toBeInTheDocument();
    expect(within(hub).getByText('A')).toBeInTheDocument(); // booted RAUC slot

    expect(screen.getByRole('article', { name: 'pi-garage' })).toHaveTextContent('Raspberry Pi 5');
    expect(await seriousViolations()).toEqual([]);
  });
});

describe('Market → Approvals', () => {
  it('Install creates an action with a uuid idempotency key and routes to Approvals', async () => {
    const { getApi } = renderApp({ token: 'owner-demo', route: '/market' });
    const user = userEvent.setup();
    expect(await seriousViolations()).toEqual([]);
    await user.click(await screen.findByRole('button', { name: 'Install Jellyfin' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument();
    const created = (await getApi().actions()).find((a) => a.params.app_id === 'jellyfin');
    expect(created?.idempotency_key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(created?.type).toBe('app.install');
    expect(await screen.findByRole('article', { name: 'Install jellyfin' })).toHaveClass('action-new');
  });

  it('an adult cannot request installs', async () => {
    renderApp({ token: 'adult-demo', route: '/market' });
    expect(await screen.findByRole('button', { name: 'Install Jellyfin' })).toBeDisabled();
  });
});

describe('Approvals', () => {
  it('shows requester kind, exact params and expiry; the owner can approve', async () => {
    const { getApi } = renderApp({ token: 'owner-demo', route: '/approvals' });
    const user = userEvent.setup();
    const card = await screen.findByRole('article', { name: 'Install ollama' });
    expect(within(card).getByText('AI agent')).toBeInTheDocument();
    expect(within(card).getByText('ops-agent')).toBeInTheDocument();
    expect(within(card).getByText(/"app_id": "ollama"/)).toBeInTheDocument();
    expect(within(card).getByText(/^in 4\dm$/)).toBeInTheDocument();
    expect(await seriousViolations()).toEqual([]);

    await user.click(within(card).getByRole('button', { name: 'Approve Install ollama' }));
    expect(await screen.findByText('Install ollama: succeeded.')).toBeInTheDocument();
    expect((await getApi().apps()).find((a) => a.id === 'ollama')?.installed).toBe(true);
  });

  it('the owner can deny', async () => {
    renderApp({ token: 'owner-demo', route: '/approvals' });
    const user = userEvent.setup();
    const card = await screen.findByRole('article', { name: 'Install ollama' });
    await user.click(within(card).getByRole('button', { name: 'Deny Install ollama' }));
    expect(await screen.findByText('Install ollama: cancelled.')).toBeInTheDocument();
  });

  it('approve/deny are disabled for an agent', async () => {
    renderApp({ token: 'agent-demo', route: '/approvals' });
    const card = await screen.findByRole('article', { name: 'Install ollama' });
    expect(within(card).getByRole('button', { name: /Approve/ })).toBeDisabled();
    expect(within(card).getByRole('button', { name: /Deny/ })).toBeDisabled();
    expect(screen.getByText(/only the owner can approve or deny/i)).toBeInTheDocument();
  });

  it('with an unknown role (real gateway), a 403 disables the buttons', async () => {
    renderApp({ token: 'agent-demo', route: '/approvals', knownRole: false });
    const user = userEvent.setup();
    const card = await screen.findByRole('article', { name: 'Install ollama' });
    const approve = within(card).getByRole('button', { name: /Approve/ });
    expect(approve).toBeEnabled();
    await user.click(approve);
    expect(await screen.findByText('Only the owner can approve or deny requests.')).toBeInTheDocument();
    await waitFor(() => expect(within(card).getByRole('button', { name: /Approve/ })).toBeDisabled());
  });
});

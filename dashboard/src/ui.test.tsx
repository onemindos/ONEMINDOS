import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { makeApps } from './api/fixtures';
import { MockApi } from './api/mock';
import { ApiError } from './api/types';
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

  it('a retry after a lost response reuses the idempotency key, so the hub returns the same action', async () => {
    const { getApi } = renderApp({ token: 'owner-demo', route: '/market' });
    const user = userEvent.setup();
    const api = getApi();
    const real = api.createAction.bind(api);
    const spy = vi.spyOn(api, 'createAction').mockImplementationOnce(async (req) => {
      await real(req); // the hub creates the action, then the response is lost
      throw new ApiError(0, 'network', 'connection reset');
    });
    await user.click(await screen.findByRole('button', { name: 'Install Jellyfin' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('connection reset');
    await user.click(screen.getByRole('button', { name: 'Install Jellyfin' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[1]![0].idempotency_key).toBe(spy.mock.calls[0]![0].idempotency_key);
    expect((await api.actions()).filter((a) => a.params.app_id === 'jellyfin')).toHaveLength(1);
  });

  it('shows an install in progress and does not offer a second one', async () => {
    const spy = vi.spyOn(MockApi.prototype, 'apps').mockImplementation(async () =>
      makeApps().map((a) =>
        a.id === 'jellyfin' ? { ...a, status: 'installing' } : a.id === 'ollama' ? { ...a, status: 'failed' } : a,
      ),
    );
    try {
      renderApp({ token: 'owner-demo', route: '/market' });
      const jelly = await screen.findByRole('article', { name: 'Jellyfin' });
      expect(within(jelly).getByRole('button', { name: 'Installing Jellyfin…' })).toBeDisabled();
      expect(within(jelly).getByText('Installing…')).toBeInTheDocument();
      const ollama = screen.getByRole('article', { name: 'Ollama' });
      expect(within(ollama).getByText('Last change failed')).toBeInTheDocument();
      expect(within(ollama).getByRole('button', { name: 'Install Ollama' })).toBeEnabled();
    } finally {
      spy.mockRestore();
    }
  });

  it('an adult cannot request installs', async () => {
    renderApp({ token: 'adult-demo', route: '/market' });
    expect(await screen.findByRole('button', { name: 'Install Jellyfin' })).toBeDisabled();
  });
});

describe('Market trust info (§11.4)', () => {
  it('a card shows links, licence, tier and last scan next to Install', async () => {
    renderApp({ token: 'owner-demo', route: '/market' });
    const card = await screen.findByRole('article', { name: 'Jellyfin' });
    const links = within(card).getByRole('list', { name: 'Links for Jellyfin' });
    expect(within(links).getByRole('link', { name: /^Docs/ })).toHaveAttribute('href', 'https://jellyfin.org/docs/');
    expect(within(links).getByRole('link', { name: /^GitHub/ })).toHaveAttribute(
      'href',
      'https://github.com/jellyfin/jellyfin',
    );
    expect(within(links).getByRole('link', { name: /^Website/ })).toBeInTheDocument();
    expect(within(links).getByRole('link', { name: /^Support/ })).toBeInTheDocument();
    expect(within(card).getByText('GPL-2.0-only')).toBeInTheDocument();
    expect(within(card).getByText('Community')).toBeInTheDocument();
    expect(within(card).getByText(/^\d{1,2} \w{3} \d{4} · passed$/)).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Install Jellyfin' })).toBeEnabled();
    expect(await seriousViolations()).toEqual([]);
  });

  it.each([
    ['Node-RED', /more than 7 days ago/],
    ['Mosquitto', /Not scanned yet/],
    ['Zigbee2MQTT', /Failed its last security scan/],
  ])('disables Install for %s and says why', async (name, reason) => {
    renderApp({ token: 'owner-demo', route: '/market' });
    const card = await screen.findByRole('article', { name });
    const button = within(card).getByRole('button', { name: `Install ${name}` });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(reason);
    expect(within(card).getByText(reason)).toBeInTheDocument();
  });

  it('a missing scan and tier read as such; Remove is never blocked by a scan', async () => {
    const spy = vi.spyOn(MockApi.prototype, 'apps').mockImplementation(async () =>
      makeApps().map((a) => (a.id === 'uptime-kuma' ? { ...a, scan: null } : a)),
    );
    try {
      renderApp({ token: 'owner-demo', route: '/market' });
      const mosq = await screen.findByRole('article', { name: 'Mosquitto' });
      expect(within(mosq).getByText('Not scanned')).toBeInTheDocument();
      expect(within(mosq).getByText('Not rated')).toBeInTheDocument();
      const kuma = screen.getByRole('article', { name: 'Uptime Kuma' });
      expect(within(kuma).getByRole('button', { name: 'Remove Uptime Kuma' })).toBeEnabled();
    } finally {
      spy.mockRestore();
    }
  });
});

describe('App page', () => {
  it('opens from the Market card and installs from there', async () => {
    const { getApi } = renderApp({ token: 'owner-demo', route: '/market' });
    const user = userEvent.setup();
    const card = await screen.findByRole('article', { name: 'Jellyfin' });
    await user.click(within(card).getByRole('link', { name: 'Jellyfin' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Jellyfin' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Links for Jellyfin' })).toBeInTheDocument();
    expect(screen.getByText('Community')).toBeInTheDocument();
    expect(screen.getByText(/· passed$/)).toBeInTheDocument();
    expect(await seriousViolations()).toEqual([]);
    await user.click(screen.getByRole('button', { name: 'Install Jellyfin' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument();
    expect((await getApi().actions()).some((a) => a.params.app_id === 'jellyfin')).toBe(true);
  });

  it('disables Install with the reason for a failed scan', async () => {
    renderApp({ token: 'owner-demo', route: '/market/zigbee2mqtt' });
    const button = await screen.findByRole('button', { name: 'Install Zigbee2MQTT' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/Failed its last security scan/);
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(await seriousViolations()).toEqual([]);
  });

  it('says so for an unknown app', async () => {
    renderApp({ token: 'owner-demo', route: '/market/no-such-app' });
    expect(await screen.findByRole('heading', { level: 1, name: 'App not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the Market' })).toBeInTheDocument();
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

  it('a list fetched before the decision does not bring back live buttons', async () => {
    const { getApi } = renderApp({ token: 'owner-demo', route: '/approvals' });
    const user = userEvent.setup();
    const card = await screen.findByRole('article', { name: 'Install ollama' });
    const api = getApi();
    vi.spyOn(api, 'actions').mockResolvedValue(await api.actions()); // every later poll is stale
    await user.click(within(card).getByRole('button', { name: 'Approve Install ollama' }));
    expect(await screen.findByText('Install ollama: succeeded.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve Install ollama' })).toBeNull();
    const history = screen.getByRole('region', { name: 'History' });
    expect(within(within(history).getByRole('article', { name: 'Install ollama' })).getByText('succeeded')).toBeInTheDocument();
  });

  it('shows why a finished action failed', async () => {
    renderApp({ token: 'owner-demo', route: '/approvals' });
    const card = await screen.findByRole('article', { name: 'Remove uptime-kuma' });
    expect(within(card).getByText(/kubectl delete exited with status 1/)).toBeInTheDocument();
    expect(await seriousViolations()).toEqual([]);
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

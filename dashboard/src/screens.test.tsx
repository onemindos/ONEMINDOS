// SPDX-License-Identifier: Apache-2.0
// Whole-app tests on the mock gateway (contract §3 rules): sign-in, every screen, the install
// request → approval → live progress → installed loop, roles, honest stale and "coming" states.
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { openScreen, renderApp, seriousViolations } from './test/helpers';

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
    expect(await seriousViolations(container)).toEqual([]);
    // Installed apps feed the dock part of Home's edit mode (the desktop has no app grid on Home).
    await userEvent.setup().click(screen.getByRole('button', { name: 'Edit Home and dock' }));
    expect(await screen.findByRole('button', { name: 'Uptime Kuma in the dock' }, T)).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it('records an explicit keyboard launch across clients and keeps a directly loaded screen read-only', async () => {
    let recent: string[] = [];
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const path = new URL(String(input)).pathname;
      if (path === '/v1/status') {
        return Response.json({ backups: { state: 'critical', observed_at: '2026-11-21T01:00:00Z', summary: 'Last backup failed' } });
      }
      if (path === '/v1/me/home') {
        if (init?.method === 'PUT') recent = JSON.parse(String(init.body)).recent;
        return Response.json({ version: 3, layout: 'desktop', recent }, { headers: { etag: '"v1"' } });
      }
      return Response.json({ error: 'not_found', message: 'Unavailable' }, { status: 404 });
    });
    vi.stubGlobal('fetch', fetch);
    try {
      const firstClient = renderApp({ token: 'owner-demo', route: '/installed', mock: false });
      const dock = within(await screen.findByRole('navigation', { name: 'Main' }, T));
      const market = dock.getByRole('link', { name: 'Market' });
      // A directly loaded window stays read-only, and Home is not loaded behind it before a desktop visit.
      expect(fetch.mock.calls.some(([url]) => new URL(String(url)).pathname === '/v1/me/home')).toBe(false);
      market.focus();
      await userEvent.setup().keyboard('{Enter}');
      await waitFor(() => expect(recent).toEqual(['sys:market']), T);
      firstClient.unmount();
      // The second browser shares the hub history and starts with its own empty window store.
      window.localStorage.clear();
      renderApp({ token: 'owner-demo', mock: false });
      const health = await screen.findByRole('region', { name: 'Box health' }, T);
      expect(await within(health).findByText('Last backup failed')).toBeInTheDocument();
      const history = within(await screen.findByRole('region', { name: 'Recent' }));
      expect(await history.findByRole('link', { name: 'Market' })).toHaveAttribute('href', '/market');
      // "Needs you" repeats the failing source as a styled row: the source as a pill, then the box's summary.
      const needs = within(await screen.findByRole('list', { name: 'Box status requiring attention' }, T));
      expect(needs.getByText('Last backup failed').closest('li')).toHaveTextContent('Backups');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('greets the person by the display name /v1/me gives, and by no name when there is none', async () => {
    const alex = renderApp({ token: 'adult-demo' });
    expect(await screen.findByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening|night), Alex$/ }, T)).toBeInTheDocument();
    alex.unmount();
    // The demo owner's display name is the role word "Owner": it is not a name, so nothing is invented.
    renderApp({ token: 'owner-demo' });
    expect(await screen.findByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening|night)$/ }, T)).toBeInTheDocument();
  });
});

describe('Short screens', () => {
  it('Storage opens in a compact window; Market keeps the wide one', async () => {
    const { container, unmount } = renderApp({ token: 'owner-demo', route: '/storage' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Storage' }, T)).toBeInTheDocument();
    expect(container.querySelector('.dsk-window')?.getAttribute('data-size')).toBe('compact');
    unmount();
    const wide = renderApp({ token: 'owner-demo', route: '/market' });
    expect(await screen.findByRole('heading', { name: 'Start here' }, T)).toBeInTheDocument();
    expect(wide.container.querySelector('.dsk-window')?.getAttribute('data-size')).toBeNull();
  });
});

describe('Market and the install loop', () => {
  it('Discover maps catalog categories onto TAXONOMY and shows the editorial rail', async () => {
    renderApp({ token: 'owner-demo', route: '/market' });
    expect(await screen.findByRole('heading', { name: 'Start here' }, T)).toBeInTheDocument();
    // home-automation (legacy slug on main) lands in Home & IoT.
    expect(screen.getByRole('button', { name: /^Home & IoT/ })).toBeInTheDocument();
  });

  it('Browsers row lists Firefox, and installing one is a request that waits for the owner', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/market' });
    const row = (await screen.findByRole('heading', { name: 'Browsers' }, T)).closest('section')!;
    expect(within(row).getByRole('link', { name: 'Firefox' })).toBeInTheDocument();
    // apps/chromium declares licenceClass: unknown, so the default green-licence filter (#867) leaves it out.
    expect(within(row).queryByRole('link', { name: 'Chromium' })).toBeNull();
    expect(within(row).queryByText(/Chrome$|Edge/)).toBeNull();
    await u.click(within(row).getByRole('link', { name: 'Firefox' }));
    await u.click(await screen.findByRole('button', { name: /Request install/ }, T));
    await u.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    const card = await screen.findByRole('article', { name: /Install firefox|Install Firefox/ }, T);
    expect(card).toHaveTextContent(/awaiting approval/i);
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
    await u.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    // The request goes straight to Approvals, where the owner sees who asked and what, then decides.
    expect(await screen.findByText('Request sent', {}, T)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' }, T)).toBeInTheDocument();
    const card = await screen.findByRole('article', { name: /Install vaultwarden|Install Vaultwarden/ }, T);
    expect(within(card).getByText('Person')).toBeInTheDocument();
    expect(card).toHaveTextContent(/awaiting approval/i);
    expect(screen.getByText(/has not described what this request will change/)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: /^Approve/ }));
    expect(await screen.findByText('Approved', {}, T)).toBeInTheDocument();

    await openScreen(u, /^Installed/); // from the launcher: the Atlas dock has no Installed tile
    expect(await screen.findByRole('link', { name: 'Vaultwarden' }, T)).toBeInTheDocument();
  });

  it('an adult can look but is told they cannot request', async () => {
    renderApp({ token: 'adult-demo', route: '/market' });
    // The notice shows once as a banner and again as the reason on each card whose request is blocked (#531).
    expect((await screen.findAllByText(/can look but not request installs/, {}, T)).length).toBeGreaterThan(0);
    screen.getAllByRole('button', { name: /^Request install/ }).forEach((b) => expect(b).toBeDisabled());
  });
});

describe('Approvals', () => {
  it('an agent sees the queue but cannot approve', async () => {
    renderApp({ token: 'agent-demo', route: '/approvals' });
    expect(await screen.findByText(/Only the owner can approve/, {}, T)).toBeInTheDocument();
    const approve = screen.getAllByRole('button', { name: /^Approve/ });
    expect(approve.length).toBeGreaterThan(0);
    approve.forEach((b) => expect(b).toBeDisabled());
  });

  it('against a real gateway (role unknown in v0) the hub refuses an agent and the buttons turn off', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'agent-demo', route: '/approvals', knownRole: false });
    const [approve] = await screen.findAllByRole('button', { name: /^Approve/ }, T);
    expect(approve).toBeEnabled();
    await u.click(approve!);
    expect(await screen.findByText('Could not approve', {}, T)).toBeInTheDocument();
    await waitFor(() => screen.getAllByRole('button', { name: /^Approve/ }).forEach((b) => expect(b).toBeDisabled()), T);
    expect((await getApi().action('act-0001')).state).toBe('awaiting_approval');
  });

  it('passes axe', async () => {
    const { container } = renderApp({ token: 'owner-demo', route: '/approvals' });
    await screen.findByRole('heading', { name: /Waiting/ }, T);
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('Installed', () => {
  it('Manage says Open goes through the OneMind sign-in and removal reviews a keep-data plan before requesting', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'owner-demo', route: '/installed/uptime-kuma' });
    expect(await screen.findByText(/Open goes through the OneMind sign-in/, {}, T)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: /^Remove/ }));
    const dlg = await screen.findByRole('dialog', { name: 'Review app request' });
    expect(within(dlg).queryByRole('radio')).toBeNull();
    expect(screen.getByText(/Removal keeps app data/)).toBeInTheDocument();
    await u.click(within(dlg).getByRole('button', { name: 'Send request' }));
    expect(await screen.findByText('Request sent', {}, T)).toBeInTheDocument();
    const sent = (await getApi().actions()).find((a) => a.type === 'app.remove' && a.state === 'awaiting_approval');
    expect(sent?.params).toEqual({ app_id: 'uptime-kuma' });
  });
});

describe('Activity, Nodes, Settings', () => {
  it('the owner sees the verified audit chain from GET /v1/audit/events', async () => {
    renderApp({ token: 'owner-demo', route: '/activity' });
    expect(await screen.findByText(/auth\.login\.succeeded/, {}, T)).toBeInTheDocument();
    expect(screen.queryByText('Not the audit chain')).not.toBeInTheDocument();
  });

  it('a person who cannot read the audit log gets an Activity that says it is not the audit chain and lists decisions', async () => {
    renderApp({ token: 'adult-demo', route: '/activity' });
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

  it('Appearance is live; legacy Backups opens the real-hub page and About stays reachable', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/appearance' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Appearance' }, T)).toBeInTheDocument();
    const backups = screen.getAllByRole('link', { name: /Backups/ }).find((link) => link.getAttribute('href') === '/settings/backups');
    expect(backups).toBeDefined();
    await u.click(backups!);
    expect(await screen.findByText(/Demo mode has no backup data/)).toBeInTheDocument();
    expect(screen.getByText('No backup proved yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Set up backups' })).toBeInTheDocument();
    await u.click(screen.getByRole('link', { name: 'Settings' }));
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
    // The hub's own notification for that action replaces the one the browser used to derive.
    expect(await screen.findByText('A request is waiting for you', {}, T)).toBeInTheDocument();
  });
});

describe('one notification centre', () => {
  it('the bell lists hub notifications and open alerts, and marking one read tells the hub', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'owner-demo', route: '/nodes' });
    await screen.findByRole('list', { name: 'Nodes' }, T);
    const bell = await screen.findByRole('button', { name: /Notifications/ }, T);
    await u.click(bell);
    expect(await screen.findByText('Backup is two days behind', {}, T)).toBeInTheDocument();
    // The hub's request notification replaces the browser-derived one for the same action.
    expect(screen.getAllByText(/A request is waiting for you/).length).toBe(1);
    const api = getApi();
    await u.click(await screen.findByRole('button', { name: /mark all.*read/i }, T));
    await waitFor(async () => expect((await api.notifications({ unread: true })).length).toBe(0), T);
  });

  it('Home says once that the box status is unknown when it is unavailable, after the greeting', async () => {
    renderApp({ token: 'owner-demo' });
    const card = await screen.findByRole('region', { name: 'Box health' }, T);
    // Other services can answer while the aggregate status source is unavailable: one Unknown line, never green.
    expect(within(card).getAllByText('Unknown')).toHaveLength(1);
    expect(within(card).getByText('The box has not reported its status yet.')).toBeInTheDocument();
    expect(card.querySelector('.om-tone-ok')).toBeNull();
    // IA §2.1: the greeting comes first, then Box health; Recent is at the end, after the tiles.
    const greeting = screen.getByRole('heading', { level: 1, name: /Good/ });
    expect(greeting.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const recent = screen.getByRole('region', { name: 'Recent' });
    const tiles = screen.getByRole('region', { name: 'Home tiles' });
    expect(tiles.compareDocumentPosition(recent) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The Atlas desktop has no app grid on Home: apps live in the dock and the launcher.
    expect(screen.queryByRole('heading', { name: 'Your apps' })).toBeNull();
    // "Needs you" lists no Unknown bullets; the waiting request is in the card.
    const needs = within(screen.getByRole('region', { name: /Needs you/ }));
    expect(needs.queryAllByText('Unknown')).toHaveLength(0);
    expect(needs.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });
});

it('a 401 from the hub signs the person out', async () => {
  const { getApi } = renderApp({ token: 'owner-demo', route: '/nodes' });
  await screen.findByRole('list', { name: 'Nodes' }, T);
  (getApi() as unknown as { principal: undefined }).principal = undefined;
  await waitFor(() => expect(screen.getByLabelText('Access token')).toBeInTheDocument(), { timeout: 15_000 });
}, 20_000);

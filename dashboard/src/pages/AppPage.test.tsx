// SPDX-License-Identifier: Apache-2.0
import { configure, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import type { CatalogApp } from '../api/types';
import { SessionProvider } from '../session';
import { seriousViolations } from '../test/helpers';

// The page is a lazy chunk; a loaded CI machine needs more than the 1 s default.
configure({ asyncUtilTimeout: 5000 });
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } });
const appView = (over: Record<string, unknown> = {}) => ({
  id: 'uptime-kuma', health: { state: 'healthy', checked_at: '2026-11-21T12:00:00Z' },
  components: [{ name: 'web', ready: true, restarts: 1, last_restart_at: null, last_exit_reason: 'OOMKilled', pods: 1 }],
  access: { roles: ['owner', 'adult'], shared_with_me: true }, ...over,
});

function mount(route: (path: string) => Response, token = 'owner-demo', over: Partial<MockApi> = {}) {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    const u = new URL(String(url));
    paths.push(u.pathname + u.search);
    return route(u.pathname + u.search);
  }));
  const api = Object.assign(new MockApi(token), {
    appLogs: async () => 'service ready\n',
    alerts: async () => [
      { schema: 'onemind.alert/v1', id: 'a1', type: 'app.unhealthy', severity: 'warning', title: 'Kuma is slow', body: 'Checks take long.', subject: { app_id: 'uptime-kuma' }, state: 'open', occurrences: 1, flapping: false, opened_at: '', updated_at: '', resolved_at: null, fix: null, learn_more_url: null, topic: 'apps', link: null, acked_by: null, acked_at: null },
      { schema: 'onemind.alert/v1', id: 'a2', type: 'app.unhealthy', severity: 'critical', title: 'Other app down', body: '', subject: { app_id: 'vaultwarden' }, state: 'open', occurrences: 1, flapping: false, opened_at: '', updated_at: '', resolved_at: null, fix: null, learn_more_url: null, topic: 'apps', link: null, acked_by: null, acked_at: null },
    ],
    notifications: async () => [
      { id: 'n1', severity: 'info', topic: 'apps', title: 'Kuma restarted', body: 'Component web restarted.', link: '/apps/uptime-kuma', source: 'gateway', action_id: null, alert_id: null, created_at: '2026-11-20T10:00:00Z', read_at: null },
      { id: 'n2', severity: 'info', topic: 'apps', title: 'Vaultwarden restarted', body: 'x', link: '/apps/vaultwarden', source: 'gateway', action_id: null, alert_id: null, created_at: '2026-11-20T10:00:00Z', read_at: null },
    ],
  }, over);
  window.sessionStorage.setItem('onemind.token', token);
  const utils = render(<MemoryRouter initialEntries={['/apps/uptime-kuma']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: (t) => DEMO_TOKENS[t] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { paths, ...utils };
}
afterEach(() => vi.unstubAllGlobals());

const hub = (path: string) => {
  if (path === '/v1/apps/uptime-kuma') return json(appView());
  if (path === '/v1/apps/uptime-kuma/metrics') return json({ app_id: 'uptime-kuma', at: '2026-11-21T12:00:00Z', components: [{ name: 'web', cpu_millicores: 12.5, mem_mb: 180, restarts: 1 }] });
  if (path === '/v1/apps/uptime-kuma/access') return json({ app_id: 'uptime-kuma', roles: ['owner', 'adult'], people: [{ id: 'u1', display_name: 'Sam' }], auth: 'onemind' });
  if (path === '/v1/backups/snapshots?app_id=uptime-kuma') return json([{ id: 's1', taken_at: '2026-11-19T02:00:00Z', reason: 'nightly', verified_at: null }, { id: 's2', taken_at: '2026-11-20T02:00:00Z', reason: 'nightly', verified_at: '2026-11-20T03:00:00Z' }]);
  return json({}, 404);
};

describe('one app page', () => {
  it('shows the state dot with its facts and reasons, and passes axe', async () => {
    const { container } = mount(hub);
    expect(await screen.findByRole('heading', { level: 1, name: 'Uptime Kuma' })).toBeInTheDocument();
    expect(await screen.findByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('Licence')).toBeInTheDocument();
    // the licence's source duty: the upstream source is a real link on the app page
    expect(screen.getByRole('link', { name: 'https://github.com/louislam/uptime-kuma' })).toHaveAttribute('href', 'https://github.com/louislam/uptime-kuma');
    expect(await seriousViolations(container)).toEqual([]);
  });

  it('turns the dot to Unknown when the health read fails, never Healthy', async () => {
    mount((p) => (p === '/v1/apps/uptime-kuma' ? json({ error: 'x', message: 'boom' }, 500) : hub(p)));
    expect(await screen.findByText('Health could not be read.', {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
    expect(screen.queryByText('Healthy')).toBeNull();
  });

  it('warns about restarts and a hub-reported unhealthy state', async () => {
    mount((p) => (p === '/v1/apps/uptime-kuma' ? json(appView({ health: { state: 'unhealthy', reason: 'web: CrashLoopBackOff' } })) : hub(p)));
    expect(await screen.findByText('Problem')).toBeInTheDocument();
    expect(screen.getByText(/web: CrashLoopBackOff/)).toBeInTheDocument();
  });

  it('Usage tab reads this app only, from the generated metrics route', async () => {
    const { paths } = mount(hub);
    expect(await screen.findByText('12.5 millicores')).toBeInTheDocument();
    expect(screen.getByText('180 MB')).toBeInTheDocument();
    expect(paths).toContain('/v1/apps/uptime-kuma/metrics');
  });

  it('Usage tab says why a figure is missing instead of a bare "Not reported"', async () => {
    mount((path) => path === '/v1/apps/uptime-kuma/metrics'
      ? json({ app_id: 'uptime-kuma', at: '2026-11-21T12:00:00Z', reason: 'metrics-server did not answer, so the runtime has no CPU or memory figures (it may still be starting).', components: [{ name: 'web', cpu_millicores: null, mem_mb: null, restarts: 0 }] })
      : hub(path));
    expect(await screen.findByText(/metrics-server did not answer/)).toBeInTheDocument();
    expect(screen.getAllByText('Not reported').length).toBeGreaterThanOrEqual(2);
  });

  it('Usage tab does not claim "no running parts" when the hub gave a reason for an empty list', async () => {
    mount((path) => path === '/v1/apps/uptime-kuma/metrics'
      ? json({ app_id: 'uptime-kuma', at: '2026-11-21T12:00:00Z', reason: "The hub could not read this app's pods from Kubernetes.", components: [] })
      : hub(path));
    expect(await screen.findByText(/could not read this app's pods/)).toBeInTheDocument();
    expect(screen.queryByText(/no running parts/)).toBeNull();
  });

  it('Usage tab says no running parts when the list is empty and there is no reason', async () => {
    mount((path) => path === '/v1/apps/uptime-kuma/metrics'
      ? json({ app_id: 'uptime-kuma', at: '2026-11-21T12:00:00Z', reason: null, components: [] })
      : hub(path));
    expect(await screen.findByText(/no running parts/)).toBeInTheDocument();
  });

  it('Logs tab shows the gateway log lines', async () => {
    mount(hub);
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'Logs' }));
    expect(await screen.findByLabelText('Last log lines')).toHaveTextContent('service ready');
  });

  it('Alerts tab keeps only this app’s alerts and notifications', async () => {
    mount(hub);
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'Alerts' }));
    expect(await screen.findByText('Kuma is slow')).toBeInTheDocument();
    expect(await screen.findByText('Kuma restarted')).toBeInTheDocument();
    expect(screen.queryByText('Other app down')).toBeNull();
    expect(screen.queryByText('Vaultwarden restarted')).toBeNull();
  });

  it('Backups tab lists this app’s restore points newest first and says Restore is a request', async () => {
    mount(hub);
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'Backups' }));
    const rows = await screen.findAllByRole('row');
    expect(within(rows[1]!).getAllByText('2026-11-20')).toHaveLength(2);
    expect(within(rows[2]!).getByText('Not checked yet')).toBeInTheDocument();
    expect(screen.getByText(/Restoring is a request an owner approves/)).toBeInTheDocument();
  });

  it('Access tab shows the roles and people, read only', async () => {
    mount(hub);
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'Access' }));
    expect(await screen.findByText('owner, adult')).toBeInTheDocument();
    expect(screen.getByText('Sam')).toBeInTheDocument();
    expect(screen.getByText('OneMind sign-in')).toBeInTheDocument();
    expect(screen.getByText('You can open it')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /share|save|change/i })).toBeNull();
  });

  it('Trust and Help tabs show the scan and only safe project links', async () => {
    mount(hub);
    const u = userEvent.setup();
    await u.click(await screen.findByRole('tab', { name: 'Trust' }));
    expect(await screen.findByText('Last security scan')).toBeInTheDocument();
    await u.click(screen.getByRole('tab', { name: 'Help' }));
    expect(await screen.findByRole('link', { name: 'Documentation' })).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('the Needs line reads machine_needs, so a new-spelling app that needs a GPU and 32 GB says so (#724)', async () => {
    const base = new MockApi('owner-demo');
    const apps = async () => (await base.apps()).map((a) => a.id !== 'uptime-kuma' ? a : {
      ...a,
      requires: { memoryMb: 32768, accelerator: { capability: 'gpu-compute' } } as CatalogApp['requires'],
      machine_needs: { requires: { arch: ['amd64'], memoryMb: 32768, accelerator: { capability: 'gpu-compute' } }, recommends: {}, supports: {} },
    });
    mount(hub, 'owner-demo', { apps });
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'Trust' }));
    const row = (await screen.findByText('Needs')).parentElement as HTMLElement;
    expect(within(row).getByText('a GPU, 32768 MB of memory')).toBeInTheDocument();
    expect(within(row).queryByText('Nothing special')).toBeNull();
  });

  it('Workloads tab is for owners and adults and has no button that changes anything', async () => {
    mount(hub);
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'Workloads' }));
    const table = await screen.findByRole('table', { name: /read only/ });
    expect(within(table).getByText('OOMKilled')).toBeInTheDocument();
    expect(within(table).queryByRole('button')).toBeNull();
  });

  it('a guest sees no Workloads tab', async () => {
    mount(hub, 'guest-demo');
    expect(await screen.findByRole('tab', { name: 'Usage' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Workloads' })).toBeNull();
  });
});

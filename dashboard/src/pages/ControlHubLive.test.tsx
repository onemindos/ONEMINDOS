// SPDX-License-Identifier: Apache-2.0
// FD-05 (#502): the Control Hub as the live board. Each panel renders from the hub, an event from
// GET /v1/events refreshes the panels it touches well before the 30 s poll, the poll carries on
// when there is no stream, a failed or old answer shows as stale, and Simple mode has no Kubernetes.
import { act, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { ApiError } from '../api/types';
import type { AlertInfo } from '../api/wiring';
import { SessionProvider } from '../session';
import { renderApp, seriousViolations } from '../test/helpers';
import { BOARD_POLL_MS, BURST_MS, STALE_AFTER_S, boardPanels, feedsFor, staleNote } from './ControlHubLive';
import { slotsOf } from './ControlHubPanels';

const T = { timeout: 4000 };
/** Well under the 30 s poll: a change seen within this came from the event, not the poll. */
const EVENT_T = { timeout: BURST_MS + 2500 };

type Listener = (type: string) => void;
/** A stand-in for the SDK subscription to GET /v1/events: tests push event types into it. */
function fakeStream() {
  const listeners = new Set<Listener>();
  const watchEvents = vi.fn((onEvent: Listener, signal: AbortSignal) => {
    listeners.add(onEvent);
    return new Promise<void>((resolve) => signal.addEventListener('abort', () => { listeners.delete(onEvent); resolve(); }, { once: true }));
  });
  const emit = (type: string) => act(() => { for (const l of listeners) l(type); });
  return { watchEvents, emit };
}

const proto = MockApi.prototype as unknown as Record<string, unknown>;
afterEach(() => {
  delete proto.watchEvents;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const region = (name: string) => screen.findByRole('region', { name }, T);
const alert = (over: Partial<AlertInfo>): AlertInfo => ({
  schema: 'onemind.alert/v1', id: 'alr_new', type: 'node.offline', severity: 'critical', title: 'pi-garage stopped reporting', body: '', subject: {}, state: 'open',
  occurrences: 1, flapping: false, opened_at: new Date().toISOString(), updated_at: new Date().toISOString(), resolved_at: null, fix: null, learn_more_url: null, topic: null, link: null, acked_by: null, acked_at: null, ...over,
});

describe('board rules', () => {
  it('Simple mode hides Kubernetes; Pro shows it; an unknown role gets the simple set', () => {
    expect(boardPanels('pro')).toContain('kubernetes');
    expect(boardPanels('simple')).not.toContain('kubernetes');
    expect(boardPanels('unknown')).not.toContain('kubernetes');
    for (const p of ['summary', 'alerts', 'apps', 'nodes', 'storage', 'backups', 'slots'] as const) expect(boardPanels('simple')).toContain(p);
  });

  it('an event refreshes only the panels it changes', () => {
    expect(feedsFor('alert.opened')).toEqual(['alerts', 'summary']);
    expect(feedsFor('node.status')).toEqual(['nodes', 'summary']);
    expect(feedsFor('app.health')).toEqual(['apps', 'summary']);
    expect(feedsFor('action.state_changed')).toEqual(expect.arrayContaining(['actions', 'storage', 'backups']));
    expect(feedsFor('notification.created')).toEqual([]);
  });

  it('a panel is stale after a failed refresh or three missed polls, never before it has data', () => {
    const now = 1_000_000;
    expect(staleNote({ data: undefined, error: undefined, fetchedAt: undefined }, now)).toBeUndefined();
    expect(staleNote({ data: 1, error: undefined, fetchedAt: now - 10_000 }, now)).toBeUndefined();
    expect(staleNote({ data: 1, error: new ApiError(0, 'network', 'down'), fetchedAt: now - 40_000 }, now)).toMatch(/^Could not refresh: showing what the hub said 40 s ago/);
    expect(staleNote({ data: 1, error: undefined, fetchedAt: now - STALE_AFTER_S * 1000 }, now)).toMatch(/^Not refreshed since 1 min ago/);
    expect(STALE_AFTER_S * 1000).toBe(3 * BOARD_POLL_MS);
  });

  it('reads RAUC slots from the heartbeat and drops malformed entries', () => {
    const rauc = { present: true, booted_slot: 'A', slots: [{ name: 'rootfs.0', state: 'booted', boot_status: 'good', bundle_version: '1.0.0' }, { state: 'inactive' }, 'x', null] };
    expect(slotsOf({ rauc })).toEqual([{ name: 'rootfs.0', state: 'booted', boot_status: 'good', bundle_version: '1.0.0' }]);
  });
});

describe('Control Hub live board', () => {
  it('shows every panel from the hub; with no event stream it says it refreshes every 30 s', async () => {
    const { container } = renderApp({ token: 'owner-demo', route: '/control-hub' });
    const alerts = await region('Alerts');
    expect(await within(alerts).findByText('Less than 10% free on /data', undefined, T)).toBeInTheDocument();
    // Critical first.
    const items = within(within(alerts).getByRole('list', { name: 'Open alerts' })).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('critical');
    expect(within(await region('App health')).getByRole('table', { name: 'Workloads' })).toBeInTheDocument();
    expect(within(await region('Machines')).getByRole('table', { name: 'Machines' })).toBeInTheDocument();
    expect(await within(await region('System slots')).findByText(/running slot A/, undefined, T)).toBeInTheDocument();
    expect(await within(await region('Kubernetes')).findAllByText(/^ready$/, undefined, T)).not.toHaveLength(0);
    // The demo gateway has no storage or backup service: said plainly, nothing invented.
    expect(await within(await region('Storage')).findByText('This box does not report storage.', undefined, T)).toBeInTheDocument();
    expect(await within(await region('Backups')).findByText('This box does not report backups.', undefined, T)).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Board updates' })).toHaveTextContent('Refreshing every 30 s');
    expect(await seriousViolations(container)).toEqual([]);
  }, 20000);

  it('an alert event from GET /v1/events shows the new alert at once, not at the next poll', async () => {
    const stream = fakeStream();
    proto.watchEvents = stream.watchEvents;
    const view = renderApp({ token: 'owner-demo', route: '/control-hub' });
    const alerts = await region('Alerts');
    await within(alerts).findByText('Less than 10% free on /data', undefined, T);
    expect(screen.getByRole('status', { name: 'Board updates' })).toHaveTextContent('Live');
    const api = view.getApi();
    const before = await api.alerts('open');
    Object.assign(api, { alerts: async () => [...before, alert({})] });
    stream.emit('alert.opened');
    expect(await within(alerts).findByText('pi-garage stopped reporting', undefined, EVENT_T)).toBeInTheDocument();
  }, 20000);

  it('a node.status event refreshes the machines and their A/B slot', async () => {
    const stream = fakeStream();
    proto.watchEvents = stream.watchEvents;
    const view = renderApp({ token: 'owner-demo', route: '/control-hub' });
    const slots = await region('System slots');
    await within(slots).findByText(/running slot A/, undefined, T);
    const api = view.getApi();
    const nodes = await api.nodes();
    Object.assign(api, { nodes: async () => nodes.map((n) => (n.rauc.present ? { ...n, rauc: { ...n.rauc, booted_slot: 'B' } } : n)) });
    stream.emit('node.status');
    expect(await within(slots).findByText(/running slot B/, undefined, EVENT_T)).toBeInTheDocument();
  }, 20000);

  it('a refresh that fails keeps the last answer and marks the panel stale', async () => {
    const stream = fakeStream();
    proto.watchEvents = stream.watchEvents;
    const view = renderApp({ token: 'owner-demo', route: '/control-hub' });
    const alerts = await region('Alerts');
    await within(alerts).findByText('Less than 10% free on /data', undefined, T);
    expect(within(alerts).queryByText(/Could not refresh/)).toBeNull();
    Object.assign(view.getApi(), { alerts: async () => { throw new ApiError(0, 'network', 'the hub did not answer'); } });
    stream.emit('alert.updated');
    expect(await within(alerts).findByText(/Could not refresh: showing what the hub said/, undefined, EVENT_T)).toBeInTheDocument();
    expect(within(alerts).getByText('Less than 10% free on /data')).toBeInTheDocument();
  }, 20000);

  it('Simple mode hides Kubernetes: a child gets the role notice and no cluster detail', async () => {
    renderApp({ token: 'child-demo', route: '/control-hub' });
    expect(await screen.findByText(/for the people who run this box/, undefined, T)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Kubernetes' })).toBeNull();
    expect(screen.queryByText(/Kubernetes/)).toBeNull();
  });
});

describe('Control Hub on a real gateway (storage and backups through @onemind/sdk)', () => {
  const storage = { node_id: 'n1', enabled: true, available: true, state: 'healthy', encrypted: true, used_bytes: 4_200_000_000, members: [{}, {}] };
  const backups = { health: 'ok', last_success_at: new Date(Date.now() - 2 * 3600_000).toISOString(), last_verified_restore_at: null, destinations: [{ kind: 's3', label: 'Off-site' }] };
  function mount(paths: Record<string, () => unknown>, stream?: ReturnType<typeof fakeStream>) {
    const fetch = vi.fn(async (url: string | URL | Request) => {
      const path = new URL(String(url instanceof Request ? url.url : url)).pathname;
      const body = paths[path];
      return body ? new Response(JSON.stringify(body()), { status: 200, headers: { 'content-type': 'application/json' } }) : new Response(JSON.stringify({ error: 'not_found', message: 'no route' }), { status: 404, headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetch);
    if (stream) proto.watchEvents = stream.watchEvents;
    window.sessionStorage.setItem('onemind.token', 'owner-demo');
    render(<MemoryRouter initialEntries={['/control-hub']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
    return (path: string) => fetch.mock.calls.filter(([u]) => new URL(String(u instanceof Request ? u.url : u)).pathname === path).length;
  }

  it('shows storage and backups as the hub reports them', async () => {
    mount({ '/v1/storage': () => storage, '/v1/backups/status': () => backups });
    const s = await region('Storage');
    expect(await within(s).findByText('healthy', undefined, T)).toBeInTheDocument();
    expect(within(s).getByText('4.2 GB')).toBeInTheDocument();
    expect(within(s).getByText('2')).toBeInTheDocument();
    const b = await region('Backups');
    expect(await within(b).findByText('2 h ago', undefined, T)).toBeInTheDocument();
    expect(within(b).getByText('never proved')).toBeInTheDocument();
  }, 20000);

  it('an action event re-reads storage and backups at once', async () => {
    const stream = fakeStream();
    let state = 'healthy';
    const count = mount({ '/v1/storage': () => ({ ...storage, state }), '/v1/backups/status': () => backups }, stream);
    const s = await region('Storage');
    await within(s).findByText('healthy', undefined, T);
    state = 'degraded';
    stream.emit('action.state_changed');
    expect(await within(s).findByText('degraded', undefined, EVENT_T)).toBeInTheDocument();
    expect(count('/v1/storage')).toBe(2);
  }, 20000);

  it('without an event stream every panel still re-reads every 30 s', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    const count = mount({ '/v1/storage': () => storage, '/v1/backups/status': () => backups });
    await within(await region('Storage')).findByText('healthy', undefined, T);
    expect(screen.getByRole('status', { name: 'Board updates' })).toHaveTextContent('Refreshing every 30 s');
    const first = { storage: count('/v1/storage'), backups: count('/v1/backups/status') };
    await act(async () => { await vi.advanceTimersByTimeAsync(BOARD_POLL_MS - 1); });
    expect(count('/v1/storage')).toBe(first.storage);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    // vi.waitFor keeps real timers, so it still re-checks while setInterval is faked.
    await vi.waitFor(() => expect(count('/v1/storage')).toBe(first.storage + 1), T);
    expect(count('/v1/backups/status')).toBe(first.backups + 1);
  }, 20000);
});

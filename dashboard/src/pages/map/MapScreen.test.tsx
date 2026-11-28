// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineRecord, NodeRecord } from '../../api/types';
import { labelHasAge } from './model';
import { MapScreen } from './MapScreen';

const NOW = Date.parse('2026-11-28T12:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const LAT = 45, LON = 10;
const at = (x: number, y: number) => ({ x, y, lat: LAT + y / 110_574, lon: LON + x / (111_320 * Math.cos((LAT * Math.PI) / 180)) });

const state = vi.hoisted(() => ({
  nodes: [] as NodeRecord[],
  machines: [] as MachineRecord[],
  sites: [] as unknown[],
  assets: [] as unknown[],
  paths: [] as string[],
  view: 'pro' as 'pro' | 'simple',
  /** Events per connection; the last one is repeated. null for a connection that ends after its events. */
  connections: undefined as { events: unknown[]; close?: boolean }[] | undefined,
  snapshotState: 'ready' as string | undefined,
}));
vi.mock('../../shell/Shell', () => ({ useShell: () => ({ view: state.view }) }));
vi.mock('../../session', () => ({
  useSignedIn: () => ({ token: 'fixture', mock: false, api: { machines: async () => state.machines } }),
  useSession: () => ({ signOut: vi.fn() }),
}));
vi.mock('../../data/hub', () => ({
  useHub: () => ({
    now: NOW,
    nodes: { data: state.nodes, error: undefined },
    instance: { data: { name: 'Home', version: '1', hub_node_id: 'hub' } },
    nodeStatus: (n: NodeRecord) => n.status,
  }),
}));

const sse = (events: unknown[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
/** An event stream that stays open (like the gateway's) until the client aborts, or closes when asked. */
function stream(events: unknown[], signal: AbortSignal | undefined, close = false): Response {
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      c.enqueue(new TextEncoder().encode(sse(events)));
      if (close) c.close();
      else signal?.addEventListener('abort', () => { try { c.error(new DOMException('aborted', 'AbortError')); } catch { /* closed */ } });
    },
  });
  return new Response(body, { headers: { 'content-type': 'text/event-stream' } });
}
let connection = 0;

beforeEach(() => {
  state.nodes = []; state.machines = []; state.sites = []; state.assets = []; state.paths = [];
  state.view = 'pro'; state.connections = undefined; state.snapshotState = 'ready'; connection = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    state.paths.push(`${u.pathname}${u.search}`);
    if (u.pathname === '/v1/sites') return Response.json(state.sites);
    if (u.pathname === '/v1/map/packs') return Response.json({ packs: [], free_bytes: null });
    if (u.pathname === '/v1/events') {
      if (state.connections) {
        const c = state.connections[Math.min(connection++, state.connections.length - 1)]!;
        return stream(c.events, init?.signal ?? undefined, c.close);
      }
      const done = state.snapshotState === undefined ? [] : [{ type: 'stream.snapshot', data: { count: state.assets.length, state: state.snapshotState } }];
      return stream([...state.assets, ...done], init?.signal ?? undefined);
    }
    return Response.json({ error: 'not_found', message: 'nope' }, { status: 404 });
  }));
});
afterEach(() => vi.unstubAllGlobals());

const show = () => render(<MemoryRouter><MapScreen /></MemoryRouter>);
const asset = (cls: string, id: string, field: string, datapoint: Record<string, unknown>) => ({ type: 'asset.value', subject: { asset_class: cls, asset_id: id, field }, data: { snapshot: true, datapoint } });

describe('Map', () => {
  it('shows an empty state, never sample assets, when nothing has reported and no place exists', async () => {
    show();
    expect(await screen.findByText('Draw your first place')).toBeVisible();
    expect(await screen.findByText(/No assets yet/)).toBeVisible();
    expect(await screen.findByText('Live')).toBeVisible();
    expect(document.querySelectorAll('.dash-map-marker')).toHaveLength(0);
    expect(state.paths).toContain('/v1/events?types=asset.*');
  });

  it('draws the box, nodes, machines and assets with an age on every label, and opens the asset card', async () => {
    state.sites = [{ id: 'home', name: 'Rivera Home', anchors: [at(0, 0), at(40, 0), at(0, 30)], floors: [{ id: 'ground', name: 'House ground' }], areas: [{ id: 'kitchen', name: 'Kitchen', floor_id: 'ground' }] }];
    state.nodes = [
      { node_id: 'hub', hostname: 'hub', role: 'hub', status: 'online', last_seen: ago(12) } as NodeRecord,
      { node_id: 'garage-pi', hostname: 'garage-pi', role: 'node', status: 'offline', last_seen: ago(400) } as NodeRecord,
    ];
    state.machines = [{ name: 'lab-vm', node_id: 'hub', ram_mb: 2048, cpus: 2, disk_gb: 20, state: 'running', created_at: ago(900), updated_at: ago(60) }];
    state.assets = [
      asset('sensor', 'greenhouse-air', 'temp', { schema: 'onemind.datapoint/v1', time: ago(8), value: 31.8, unit: 'Cel', quality: 'live', position: at(10, 5) }),
      asset('door', 'front', 'state', { schema: 'onemind.datapoint/v1', time: ago(400), value: 'locked', quality: 'live', pose: { frame: 'ground', x: 2, y: 3 } }),
    ];
    const u = userEvent.setup();
    show();
    const plan = await screen.findByRole('region', { name: 'Plan of Rivera Home' });
    expect(await within(plan).findByText('greenhouse-air · 31.8 °C · 8 s')).toBeVisible();
    expect(within(plan).getByText('front · locked · stale 6 min')).toBeVisible();
    const shelf = screen.getByRole('region', { name: 'Not on the plan yet' });
    expect(within(shelf).getByText('hub · online · 12 s')).toBeVisible();
    expect(within(shelf).getByText('lab-vm · running · 12 s')).toBeVisible();
    expect(within(shelf).getByText('garage-pi · off 6 min')).toBeVisible();
    for (const label of document.querySelectorAll('[data-map-label]')) expect(labelHasAge(label.textContent ?? ''), label.textContent ?? '').toBe(true);
    expect(screen.getByRole('button', { name: /Stale 1/ })).toBeVisible();
    expect(screen.getByText('Kitchen')).toBeVisible();

    await u.click(within(shelf).getByRole('button', { name: /lab-vm/ }));
    const card = screen.getByRole('complementary', { name: 'lab-vm details' });
    expect(within(card).getByText(/Read only/)).toBeVisible();
    expect(within(card).getByRole('link', { name: 'Open Machines' })).toHaveAttribute('href', '/machines');
    expect(within(card).getByText(/2 CPU · 2 GB RAM · 20 GB disk/)).toBeVisible();
  });

  it('switches layers off, filters by state and lists every item for the keyboard', async () => {
    state.sites = [{ id: 'home', name: 'Home', anchors: [at(0, 0), at(40, 0), at(0, 30)] }];
    state.nodes = [{ node_id: 'hub', hostname: 'hub', role: 'hub', status: 'online', last_seen: ago(12) } as NodeRecord];
    state.assets = [asset('sensor', 'air', 'temp', { time: ago(8), value: 20, unit: 'Cel', quality: 'live', position: at(10, 5) })];
    const u = userEvent.setup();
    show();
    expect(await screen.findByText('air · 20 °C · 8 s')).toBeVisible();
    await u.click(screen.getByRole('switch', { name: /Sensor/ }));
    expect(screen.queryByText('air · 20 °C · 8 s')).toBeNull();
    await u.click(screen.getByRole('switch', { name: /Sensor/ }));
    await u.click(screen.getByRole('button', { name: /Offline 0/ }));
    expect(screen.queryByText('air · 20 °C · 8 s')).toBeNull();
    await u.click(screen.getByRole('button', { name: /Offline 0/ }));

    await u.click(screen.getByRole('button', { name: 'List' }));
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    within(table).getByRole('button', { name: 'air' }).focus();
    await u.keyboard('{Enter}');
    expect(screen.getByRole('complementary', { name: 'air details' })).toBeVisible();
  });

  it('says so when this account may not read asset values, and still shows the nodes', async () => {
    state.nodes = [{ node_id: 'hub', hostname: 'hub', role: 'hub', status: 'online', last_seen: ago(12) } as NodeRecord];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const p = new URL(url).pathname;
      if (p === '/v1/events') return Response.json({ error: 'permission_denied', message: 'no' }, { status: 403 });
      if (p === '/v1/sites') return Response.json([]);
      return Response.json({ error: 'unavailable', message: 'off' }, { status: 503 });
    }));
    show();
    expect(await screen.findByText('This account may not read asset values')).toBeVisible();
    expect(screen.getByText('hub · online · 12 s')).toBeVisible();
    expect(await screen.findByText(/Offline maps are not set up/, {}, { timeout: 4000 })).toBeVisible();
  });
  it('says the hub\'s asset values are pending, and never claims nothing has reported', async () => {
    state.snapshotState = 'pending';
    show();
    expect((await screen.findAllByText(/Asset values pending/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/No assets yet/)).toBeNull();
    expect(screen.queryByText('Nothing has reported yet.')).toBeNull();
  });

  it('says the hub could not read asset values when its state is error', async () => {
    state.snapshotState = 'error';
    show();
    expect((await screen.findAllByText(/Asset values unavailable/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/No assets yet/)).toBeNull();
  });

  it('draws no asset and claims no emptiness before the first complete snapshot', async () => {
    state.snapshotState = undefined; // values arrive, stream.snapshot never does
    state.assets = [asset('sensor', 'air', 'temp', { time: ago(8), value: 20, unit: 'Cel', quality: 'live' })];
    show();
    expect(await screen.findByText('Connecting to the live feed…')).toBeVisible();
    expect((await screen.findAllByText(/Waiting for the live feed/)).length).toBeGreaterThan(0);
    await new Promise((r) => setTimeout(r, 400));
    expect(screen.queryByText(/air · 20/)).toBeNull();
    expect(screen.queryByText(/No assets yet/)).toBeNull();
  });

  it('swaps in each new snapshot after a reconnect, so an asset removed meanwhile disappears', async () => {
    const a = asset('sensor', 'air', 'temp', { time: ago(8), value: 20, unit: 'Cel', quality: 'live' });
    const b = asset('sensor', 'soil', 'moisture', { time: ago(8), value: 30, unit: '%', quality: 'live' });
    const done = { type: 'stream.snapshot', data: { count: 1, state: 'ready' } };
    state.connections = [{ events: [a, b, done], close: true }, { events: [a, done] }];
    show();
    expect(await screen.findByText('soil · 30 % · 8 s')).toBeVisible();
    // Between connections the last complete map stays on screen.
    expect(await screen.findByText(/Reconnecting/)).toBeVisible();
    expect(screen.getByText('soil · 30 % · 8 s')).toBeVisible();
    await waitFor(() => expect(screen.queryByText('soil · 30 % · 8 s')).toBeNull(), { timeout: 4000 });
    expect(screen.getByText('air · 20 °C · 8 s')).toBeVisible();
    expect(screen.getByText('Live')).toBeVisible();
  });

  it('shows a loading line while places load and only the error when they fail, never the empty state', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const p = new URL(url).pathname;
      if (p === '/v1/sites') return new Promise<Response>(() => {});
      if (p === '/v1/events') return stream([{ type: 'stream.snapshot', data: { count: 0, state: 'ready' } }], init?.signal ?? undefined);
      return Response.json({ packs: [], free_bytes: null });
    }));
    const first = show();
    expect(await screen.findByText('Loading places…')).toBeVisible();
    expect(screen.queryByText('Draw your first place')).toBeNull();
    first.unmount();

    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const p = new URL(url).pathname;
      if (p === '/v1/sites') return Response.json({ error: 'permission_denied', message: 'Not yours' }, { status: 403 });
      if (p === '/v1/events') return stream([{ type: 'stream.snapshot', data: { count: 0, state: 'ready' } }], init?.signal ?? undefined);
      return Response.json({ packs: [], free_bytes: null });
    }));
    show();
    expect(await screen.findByText(/Could not read places/, {}, { timeout: 4000 })).toBeVisible();
    expect(screen.queryByText('Draw your first place')).toBeNull();
    expect(screen.queryByText('Loading places…')).toBeNull();
  });

  it('offers no Nodes or Machines link to someone who cannot open those screens', async () => {
    state.view = 'simple';
    state.nodes = [{ node_id: 'hub', hostname: 'hub', role: 'hub', status: 'online', last_seen: ago(12) } as NodeRecord];
    const u = userEvent.setup();
    show();
    await u.click(await screen.findByRole('button', { name: /hub · online/ }));
    const card = screen.getByRole('complementary', { name: 'hub details' });
    expect(within(card).queryByRole('link')).toBeNull();
  });

  it('says what the filters hide', async () => {
    state.nodes = [{ node_id: 'hub', hostname: 'hub', role: 'hub', status: 'online', last_seen: ago(12) } as NodeRecord];
    const u = userEvent.setup();
    show();
    await u.click(await screen.findByRole('switch', { name: /Box and nodes/ }));
    expect(screen.getByText(/1 hidden by the layer and state filters/)).toBeVisible();
  });
});

// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
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
}));
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

beforeEach(() => {
  state.nodes = []; state.machines = []; state.sites = []; state.assets = []; state.paths = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = new URL(url);
    state.paths.push(`${u.pathname}${u.search}`);
    if (u.pathname === '/v1/sites') return Response.json(state.sites);
    if (u.pathname === '/v1/map/packs') return Response.json({ packs: [], free_bytes: null });
    if (u.pathname === '/v1/events') {
      return new Response(sse([...state.assets, { type: 'stream.snapshot', data: { count: state.assets.length } }]), { headers: { 'content-type': 'text/event-stream' } });
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
    expect(within(plan).getByText('front · locked · 6 min')).toBeVisible();
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
});

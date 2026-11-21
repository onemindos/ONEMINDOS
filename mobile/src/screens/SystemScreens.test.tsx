// SPDX-License-Identifier: Apache-2.0
// OS updates, System controls, Device info, Live usage and Network against a fake gateway.
import { NavigationContainer } from '@react-navigation/native';
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactElement, ReactNode } from 'react';
import { Features, OP } from '../api/client';
import { INSTANCE, makeNodes } from '../api/fixtures';
import { ApiError, type Action, type OsUpdateStatus } from '../api/types';
import { HubDataProvider } from '../data';
import { hubNode, installOffer, usedPct } from '../lib/system';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { MoreScreen } from './MoreScreen';
import { DeviceInfoScreen, LiveUsageScreen, NetworkScreen, OsUpdatesScreen, SystemControlsScreen } from './SystemScreens';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const OWNER_ME = { principal: { id: 'owner', kind: 'person' as const, role: 'owner' as const }, token: null, session: null, passkeys: 0, capabilities: ['can_approve', 'can_request'] };
const GUEST_ME = { principal: { id: 'g', kind: 'person' as const, role: 'guest' as const }, token: null, session: null, passkeys: 0, capabilities: [] };

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(ui: ReactElement, ops: string[], over: Parameters<typeof v0Api>[0] = {}) {
  const api = v0Api({ features: async () => new Features(ops, 'openapi'), me: async () => OWNER_ME, actions: async () => [], ...over });
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <HubDataProvider intervalMs={0}>
          <NavigationContainer>{ui}</NavigationContainer>
        </HubDataProvider>
      </Gate>
    </SessionProvider>,
  );
  return api;
}

const slot = { name: 'rootfs.1', bootname: 'B', state: 'inactive', boot_status: 'good', bundle_version: '0.9.0' };
const status: OsUpdateStatus = {
  install: { available: false, reason: 'engine_unreachable', message: 'Install at the box with `onemind update apply`.' },
  nodes: [
    { node_id: 'hub1', hostname: 'bannerfish', status: 'online', last_seen: null, reported: true, channel: 'stable', current_version: '0.9.0', available_version: '0.9.1', state: 'idle', last_check: null, last_result: 'ok', rauc: { present: true, booted_slot: 'A', slots: [slot] } },
    { node_id: 'n2', hostname: 'spare', status: 'online', last_seen: null, reported: false, channel: null, current_version: null, available_version: null, state: null, last_check: null, last_result: null, rauc: { present: false, booted_slot: null, slots: [] } },
  ],
};

describe('OS updates', () => {
  it('is hidden-state when the hub does not serve it', async () => {
    await mount(<OsUpdatesScreen />, []);
    expect(await screen.findByText(/does not serve this yet/)).toBeTruthy();
  });

  it('shows version, slot, offer and the engine warning; machines without an update service say so', async () => {
    await mount(<OsUpdatesScreen />, [OP.me, OP.osUpdates], { osUpdates: async () => status });
    expect(await screen.findByText('Running version')).toBeTruthy();
    expect(screen.getByText('0.9.1')).toBeTruthy();
    expect(screen.getByText(/Slot B: inactive, good, version 0.9.0/)).toBeTruthy();
    expect(screen.getByText(/Installing from the hub is not available yet/)).toBeTruthy();
    expect(screen.getByText('This machine runs no update service.')).toBeTruthy();
    expect(screen.queryByTestId('os-ask-n2')).toBeNull();
  });

  it('"Ask to install" files os.update.install and says nothing was installed', async () => {
    const filed: Action = { id: 'act-9', type: 'os.update.install', params: {}, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval' };
    const createAction = jest.fn(async () => filed);
    await mount(<OsUpdatesScreen />, [OP.me, OP.osUpdates], { osUpdates: async () => status, createAction, actions: async () => [filed] });
    await fireEvent.press(await screen.findByTestId('os-ask-hub1'));
    expect(await screen.findByText(/Nothing has been installed/)).toBeTruthy();
    expect(createAction).toHaveBeenCalledTimes(1);
    const sent = (createAction.mock.calls[0] as unknown as [{ type: string; params: object }])[0];
    expect(sent.type).toBe('os.update.install');
    expect(sent.params).toEqual({ node_id: 'hub1', version: '0.9.1' });
  });

  it('a sign-in that may not request sees no button', async () => {
    await mount(<OsUpdatesScreen />, [OP.me, OP.osUpdates], { osUpdates: async () => status, me: async () => GUEST_ME });
    expect(await screen.findByText('Running version')).toBeTruthy();
    expect(screen.queryByTestId('os-ask-hub1')).toBeNull();
  });

  it('a 403 is said plainly', async () => {
    await mount(<OsUpdatesScreen />, [OP.me, OP.osUpdates], { osUpdates: async () => { throw new ApiError(403, 'permission_denied', 'no'); } });
    expect(await screen.findByText('This sign-in may not read OS updates.')).toBeTruthy();
  });
});

describe('System controls', () => {
  const plan = { policy_verdict: 'needs_approval', risk: 'actuate' as const, plan: { summary: 'Restart the box. Apps stop for about two minutes.', warnings: ['Open connections drop.'] }, plan_sha256: 'abc' };

  it('hides when the hub has no such route', async () => {
    await mount(<SystemControlsScreen />, [OP.me]);
    expect(await screen.findByText(/does not serve this yet/)).toBeTruthy();
    expect(screen.queryByTestId('control-system.restart')).toBeNull();
  });

  it('shows the plan first, then files the request bound to its hash', async () => {
    const filed: Action = { id: 'act-3', type: 'system.restart', params: {}, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval' };
    const createAction = jest.fn(async () => filed);
    const systemPlan = jest.fn(async () => plan);
    await mount(<SystemControlsScreen />, [OP.me, OP.systemPlan], { systemPlan, createAction, actions: async () => [filed] });
    await fireEvent.press(await screen.findByTestId('control-system.restart'));
    expect(await screen.findByText(/Apps stop for about two minutes/)).toBeTruthy();
    expect(screen.getByText('Open connections drop.')).toBeTruthy();
    expect(createAction).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId('control-send'));
    expect(await screen.findByText(/Nothing has happened/)).toBeTruthy();
    const sent = (createAction.mock.calls[0] as unknown as [{ type: string; plan_sha256: string }])[0];
    expect(sent).toMatchObject({ type: 'system.restart', plan_sha256: 'abc' });
  });

  it('a refused plan files nothing', async () => {
    const createAction = jest.fn();
    await mount(<SystemControlsScreen />, [OP.me, OP.systemPlan], { systemPlan: async () => ({ ...plan, policy_verdict: 'refused', reason: 'an update is installing' }), createAction });
    await fireEvent.press(await screen.findByTestId('control-system.shutdown'));
    expect(await screen.findByText(/an update is installing/)).toBeTruthy();
    expect(createAction).not.toHaveBeenCalled();
  });
});

describe('Device info', () => {
  it('shows the instance and the hub machine', async () => {
    await mount(<DeviceInfoScreen />, [OP.me], { instance: async () => ({ ...INSTANCE, name: 'home' }) });
    expect(await screen.findByText('About this box')).toBeTruthy();
    expect(await screen.findByTestId('device-hardware')).toBeTruthy();
    expect(screen.getByText('OneMind version')).toBeTruthy();
    expect(screen.getByText('Secure Boot', { exact: false })).toBeTruthy();
  });
});

describe('Live usage', () => {
  it('hides when no usage route is served', async () => {
    await mount(<LiveUsageScreen />, [OP.me]);
    expect(await screen.findByText(/does not serve this yet/)).toBeTruthy();
  });

  it('shows CPU, memory and disk per machine, and per app when the hub serves it', async () => {
    const nodes = makeNodes(Date.now());
    const id = nodes[0]!.node_id;
    await mount(<LiveUsageScreen />, [OP.me, OP.nodeMetrics, OP.appMetrics], {
      nodeMetrics: async () => ({ node_id: id, source: 'heartbeat', samples: [{ at: '', cpu_pct: 42.4, mem_used_mb: 2048, mem_total_mb: 4096, disk_free_gb: 50, disk_total_gb: 100, temp_c: null, load1: null }] }),
      apps: async () => [{ id: 'vault', name: 'Vault', installed: true, status: 'healthy' } as never],
      appMetrics: async () => ({ app_id: 'vault', at: '', components: [{ name: 'web', cpu_millicores: 12.4, mem_mb: 150, restarts: 0 }] }),
    });
    expect(await screen.findByTestId(`usage-${id}`)).toBeTruthy();
    expect(screen.getAllByText('42%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('50% of 4.0 GB').length).toBeGreaterThan(0);
    expect(screen.getAllByText('50% of 100 GB').length).toBeGreaterThan(0);
    expect(await screen.findByText('12 m CPU · 150 MB')).toBeTruthy();
  });
});

describe('Network', () => {
  it('hides when /v1/mesh is not served', async () => {
    await mount(<NetworkScreen />, [OP.me]);
    expect(await screen.findByText(/does not serve this yet/)).toBeTruthy();
  });

  it('shows names read only and says what is not reported', async () => {
    await mount(<NetworkScreen />, [OP.me, OP.mesh], { mesh: async () => ({ mode: 'lan', box: 'home', https: true, names: { lan: ['onemind.local', 'home.local'], mesh: [] } }) });
    expect(await screen.findByText('Home network (LAN)')).toBeTruthy();
    expect(screen.getByText('home.local')).toBeTruthy();
    expect(screen.getByText(/does not report network interfaces, the gateway or DNS servers yet/)).toBeTruthy();
  });
});

describe('More: System section', () => {
  it('lists only what the hub serves', async () => {
    await mount(<MoreScreen />, [OP.me, OP.osUpdates], { alerts: async () => [] });
    expect(await screen.findByTestId('more-OsUpdates')).toBeTruthy();
    expect(screen.getByTestId('more-DeviceInfo')).toBeTruthy();
    for (const k of ['SystemControls', 'LiveUsage', 'Network']) expect(screen.queryByTestId(`more-${k}`)).toBeNull();
  });
});

describe('helpers', () => {
  it('installOffer needs a reporting node and a different version', () => {
    expect(installOffer({ reported: true, available_version: '2', current_version: '1' })).toBe('2');
    expect(installOffer({ reported: true, available_version: '1', current_version: '1' })).toBeUndefined();
    expect(installOffer({ reported: false, available_version: '2', current_version: null })).toBeUndefined();
  });
  it('usedPct clamps and refuses missing numbers', () => {
    expect(usedPct(50, 200)).toBe(25);
    expect(usedPct(300, 200)).toBe(100);
    expect(usedPct(null, 200)).toBeUndefined();
    expect(usedPct(1, 0)).toBeUndefined();
  });
  it('hubNode prefers the instance hub id', () => {
    const n = makeNodes(Date.now());
    expect(hubNode(n, n[n.length - 1]!.node_id)?.node_id).toBe(n[n.length - 1]!.node_id);
    expect(hubNode([], null)).toBeUndefined();
  });
});

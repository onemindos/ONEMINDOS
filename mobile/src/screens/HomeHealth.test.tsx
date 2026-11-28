// SPDX-License-Identifier: Apache-2.0
// Home health card, live indicator and Open app, against a recorded /v1/status and a fake gateway.
import { NavigationContainer } from '@react-navigation/native';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Linking } from 'react-native';
import { Features, OP } from '../api/client';
import { makeActions, makeApps } from '../api/fixtures';
import { ApiError, type CatalogApp } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import status from '../test/status.recorded.json';
import { AppDetailScreen } from './AppDetailScreen';
import { AppsScreen } from './AppsScreen';
import { Button } from '../ui/bits';
import { setThemeChoice } from '../ui/theme';
import { tokens } from '../ui/tokens.generated';
import { HealthCard, HomeScreen } from './HomeScreen';

type Opts = { onEvent: (e: unknown) => void; onState?: (s: string) => void };
const streams: Opts[] = [];
jest.mock('../lib/events', () => ({
  ...jest.requireActual('../lib/events'),
  EventStream: class {
    constructor(o: Opts) {
      streams.push(o);
    }
    start() {
      streams[streams.length - 1]!.onState?.('connecting');
    }
    stop() {}
  },
}));

let mockParams = { id: 'uptime-kuma' };
jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useRoute: () => ({ params: mockParams }),
}));

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const OWNER_ME = { principal: { id: 'owner', kind: 'person' as const, role: 'owner' as const }, token: null, session: null, passkeys: 0, capabilities: ['can_approve', 'can_request'] };

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(ui: ReactNode, over: Parameters<typeof v0Api>[0] = {}, ops: string[] = [OP.me, OP.status, OP.events]) {
  const api = v0Api({
    features: async () => new Features(ops, 'openapi'),
    me: async () => OWNER_ME,
    actions: async () => [],
    eventsEndpoint: () => ({ url: 'https://hub.example/v1/events', bearer: () => 't' }),
    ...over,
  });
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

const kuma = (over: Partial<CatalogApp> = {}): CatalogApp => ({ ...makeApps().find((a) => a.id === 'uptime-kuma')!, ...over });

beforeEach(() => {
  streams.length = 0;
  jest.spyOn(Linking, 'openURL').mockResolvedValue();
});

it.each(['light', 'dark'] as const)('uses the action token for the primary button in %s', async (mode) => {
  setThemeChoice(mode);
  try {
    await render(<Button testID="primary" label="Continue" onPress={() => undefined} />);
    expect(screen.getByTestId('primary')).toHaveStyle({ backgroundColor: tokens[mode].action });
  } finally {
    await act(() => setThemeChoice('system'));
  }
});

it('shows the hub request and hides the sensor card when the hub has no readings', async () => {
  await mount(<HomeScreen />, {
    actions: async () => [{ ...makeActions(Date.now())[0]!, risk: 'actuate' }],
    nodeMetrics: async () => ({ node_id: 'hub', source: 'heartbeat', samples: [] }),
  }, [OP.me, OP.nodeMetrics]);
  const card = await screen.findByTestId('pending-card');
  expect(card).toHaveTextContent(/Install Ollama/i);
  expect(card).toHaveTextContent(/agent ops-agent/);
  expect(card).toHaveTextContent(/Hold to approve on the next screen/);
  expect(screen.queryByTestId('live-temperature')).toBeNull();
});

it('shows a fresh hub temperature with its age', async () => {
  const now = Date.now();
  const makeSample = (offset: number, temp_c: number) => ({
    at: new Date(now - offset).toISOString(), temp_c,
    cpu_pct: null, mem_used_mb: null, mem_total_mb: null, disk_free_gb: null, disk_total_gb: null, load1: null,
  });
  await mount(<HomeScreen />, {
    nodeMetrics: async () => ({ node_id: 'hub', source: 'heartbeat', samples: [makeSample(20_000, 43), makeSample(8000, 45.2)] }),
  }, [OP.me, OP.nodeMetrics]);
  const card = await screen.findByTestId('live-temperature');
  expect(card).toHaveTextContent(/45\.2 °C/);
  expect(card).toHaveTextContent(/Live · \d+s ago/);
});

it('omits the Needs you card when no hub request waits', async () => {
  await mount(<HomeScreen />);
  await screen.findByText('0 requests need a decision.');
  expect(screen.queryByTestId('pending-card')).toBeNull();
});

describe('Home health card', () => {
  it('renders an unknown source as Unknown, never OK', async () => {
    await mount(<HealthCard />, { status: async () => status as never });
    const row = await screen.findByTestId('health-storage');
    expect(row).toHaveTextContent(/Unknown/);
    expect(row).not.toHaveTextContent(/\bOK\b/);
    expect(screen.getByTestId('health-mesh')).toHaveTextContent(/Unknown/);
    expect(screen.getByTestId('health-alerts')).toHaveTextContent(/OK/);
  });

  it('keeps the last data and says so when a refresh fails', async () => {
    let n = 0;
    const api = await mount(<HealthCard />, {
      status: async () => {
        if (n++ === 0) return status as never;
        throw new ApiError(503, 'unavailable', 'down');
      },
    });
    expect(await screen.findByTestId('health-backups')).toBeTruthy();
    expect(screen.queryByTestId('health-error')).toBeNull();
    expect(api).toBeTruthy();
    await act(async () => streams[0]!.onEvent({ type: 'action.updated', id: '1', ts: '', schema: 'onemind.event/v1' }));
    expect(await screen.findByTestId('health-error', undefined, { timeout: 2000 })).toHaveTextContent(/Showing the last answer/);
    expect(screen.getByTestId('health-backups')).toHaveTextContent(/Last backup 1h ago/);
  });

  it('shows no card and no error to a role the gateway refuses the status read (teen, child, guest)', async () => {
    await mount(<HealthCard />, {
      status: async () => {
        throw new ApiError(403, 'permission_denied', 'not allowed');
      },
    });
    await act(async () => new Promise((r) => setTimeout(r, 200)));
    expect(screen.queryByTestId('health-card')).toBeNull();
    expect(screen.queryByTestId('health-error')).toBeNull();
  });

  it('shows nothing when the hub has no status route', async () => {
    await mount(<HealthCard />, {}, [OP.me]);
    expect(screen.queryByTestId('health-card')).toBeNull();
  });

  it('the indicator follows the stream and an event refreshes the status', async () => {
    const statusFn = jest.fn(async () => status as never);
    await mount(<HealthCard />, { status: statusFn });
    await screen.findByTestId('health-card');
    expect(screen.getByTestId('live-indicator')).toHaveTextContent(/Reconnecting/);
    await act(async () => streams[0]!.onState?.('open'));
    expect(screen.getByTestId('live-indicator')).toHaveTextContent(/Live/);
    await act(async () => streams[0]!.onState?.('retrying'));
    expect(screen.getByTestId('live-indicator')).toHaveTextContent(/Reconnecting/);
    const before = statusFn.mock.calls.length;
    await act(async () => streams[0]!.onEvent({ type: 'action.updated', id: '1', ts: '', schema: 'onemind.event/v1' }));
    await screen.findByTestId('health-card');
    await act(async () => new Promise((r) => setTimeout(r, 500)));
    expect(statusFn.mock.calls.length).toBeGreaterThan(before);
  });

  it('says Polling when the hub has no event stream', async () => {
    await mount(<HealthCard />, { status: async () => status as never, eventsEndpoint: () => undefined });
    await screen.findByTestId('health-card');
    expect(screen.getByTestId('live-indicator')).toHaveTextContent(/Polling/);
  });
});

describe('Open app', () => {
  it('Apps shows Open only for an installed app with a web address, and opens it in the browser', async () => {
    const apps = [kuma(), kuma({ id: 'noport', name: 'No Port', web_port: null }), kuma({ id: 'avail', name: 'Not Installed', installed: false, status: 'not_installed' })];
    await mount(<AppsScreen />, { apps: async () => apps });
    fireEvent.press(await screen.findByTestId('open-uptime-kuma'));
    expect(Linking.openURL).toHaveBeenCalledWith('https://hub.example:3001/');
    expect(screen.queryByTestId('open-noport')).toBeNull();
    expect(screen.queryByTestId('open-avail')).toBeNull();
  });

  it('App detail shows Open app only with an address', async () => {
    mockParams = { id: 'uptime-kuma' };
    await mount(<AppDetailScreen />, { apps: async () => [kuma()] });
    fireEvent.press(await screen.findByTestId('open-app'));
    expect(Linking.openURL).toHaveBeenCalledWith('https://hub.example:3001/');
  });

  it('App detail hides Open app for an app without a web port', async () => {
    mockParams = { id: 'uptime-kuma' };
    await mount(<AppDetailScreen />, { apps: async () => [kuma({ web_port: null })] });
    expect(await screen.findByTestId('app-detail')).toBeTruthy();
    expect(screen.queryByTestId('open-app')).toBeNull();
  });
});

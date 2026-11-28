// SPDX-License-Identifier: Apache-2.0
// The Map tab against the real stream parser path: events are fed through the mocked EventStream, sites through a fake api.
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { Features, OP } from '../api/client';
import { MapScreen } from './MapScreen';

type Opts = { onEvent: (e: unknown) => void; onState?: (s: string) => void; types?: string[] };
const streams: Opts[] = [];
jest.mock('../lib/events', () => ({
  ...jest.requireActual('../lib/events'),
  EventStream: class {
    constructor(o: Opts) {
      streams.push(o);
    }
    start() {}
    stop() {}
  },
}));

const mockSites = jest.fn();
// One stable session object, as the real provider gives (the stream effect depends on it).
const mockSession = {
  api: { eventsEndpoint: () => ({ url: 'https://hub/v1/events', bearer: () => 't' }), sites: (...a: unknown[]) => mockSites(...a) },
  features: undefined as unknown,
};
jest.mock('../session', () => ({ useSignedIn: () => mockSession }));
jest.mock('../data', () => ({
  useHubData: () => ({ refreshing: false, reload: async () => undefined, hubOffsetMs: 0 }),
  useNow: () => Date.now(),
}));

const snap = (count: number, state = 'ready') => ({ schema: 'onemind.event/v1', id: 's', type: 'stream.snapshot', ts: '', data: { count, state } });

const val = (id: string, field: string, revision: number, value: unknown, ageS: number, extra: object = {}) => ({
  schema: 'onemind.event/v1',
  id: `asset:${revision}`,
  type: 'asset.value',
  ts: new Date().toISOString(),
  subject: { asset_id: id, asset_class: 'sensor', field },
  data: { revision, snapshot: true, datapoint: { schema: 'onemind.datapoint/v1', nats_subject: 'x', time: new Date(Date.now() - ageS * 1000).toISOString(), quality: 'live', source: { kind: 'node', id: 'n' }, value, unit: 'Cel', ...extra } },
});

beforeAll(() => {
  mockSession.features = new Features(new Set([OP.events, OP.sites]), 'openapi');
});

beforeEach(() => {
  streams.length = 0;
  mockSites.mockReset().mockResolvedValue([]);
});

it('subscribes to asset.* only, through the gateway', async () => {
  await render(<MapScreen />);
  expect(streams[0]!.types).toEqual(['asset.*']);
  await act(async () => {});
});

it('says nothing exists only after a ready, empty snapshot on an open stream', async () => {
  await render(<MapScreen />);
  await act(async () => {
    streams[0]!.onState?.('connecting');
  });
  expect(screen.queryByTestId('map-empty')).toBeNull();
  await act(async () => {
    streams[0]!.onState?.('open'); // open, no snapshot yet: still loading
  });
  expect(screen.queryByTestId('map-empty')).toBeNull();
  await act(async () => {
    streams[0]!.onEvent(snap(0, 'pending')); // the box's asset store is not ready
  });
  expect(screen.queryByTestId('map-empty')).toBeNull();
  expect(screen.getByText(/asset store is still starting/)).toBeTruthy();
  await act(async () => {
    streams[0]!.onEvent(snap(0, 'error'));
  });
  expect(screen.queryByTestId('map-empty')).toBeNull();
  expect(screen.getByText(/asset store isn't available/)).toBeTruthy();
  await act(async () => {
    streams[0]!.onEvent(snap(0, 'ready'));
  });
  expect(screen.getByTestId('map-empty')).toBeTruthy();
  expect(screen.queryByTestId('map-plan')).toBeNull();
});

it.each(['forbidden', 'unsupported', 'unauthenticated'])('gives one notice and no empty card when the stream is %s', async (st) => {
  await render(<MapScreen />);
  await act(async () => {
    streams[0]!.onState?.(st);
  });
  expect(screen.queryByTestId('map-empty')).toBeNull();
  expect(screen.queryByText(/Nothing on the map yet/)).toBeNull();
  expect(screen.getAllByText(/box|allowed|connected/i).length).toBe(1); // exactly one notice
});

it('drops an asset removed while the phone was disconnected, once the new snapshot arrives', async () => {
  jest.useFakeTimers();
  await render(<MapScreen />);
  await act(async () => {
    streams[0]!.onState?.('open');
    streams[0]!.onEvent(val('air', 'temperature', 1, 20, 3));
    streams[0]!.onEvent(val('door', 'locked', 2, true, 3, { unit: undefined }));
    streams[0]!.onEvent(snap(2));
  });
  await fireEvent.press(screen.getByTestId('view-list'));
  expect(screen.getByTestId('row-sensor.door')).toBeTruthy();
  await act(async () => {
    streams[0]!.onState?.('retrying'); // dropped: the last map stays
  });
  expect(screen.getByTestId('row-sensor.door')).toBeTruthy();
  await act(async () => {
    streams[0]!.onState?.('open');
    streams[0]!.onEvent(val('air', 'temperature', 3, 21, 1)); // smaller snapshot: the door is gone
    streams[0]!.onEvent(snap(1));
  });
  expect(screen.queryByTestId('row-sensor.door')).toBeNull();
  expect(screen.getByTestId('row-sensor.air')).toBeTruthy();
  jest.useRealTimers();
});

it('warns when the snapshot count does not match the values received', async () => {
  await render(<MapScreen />);
  await act(async () => {
    streams[0]!.onState?.('open');
    streams[0]!.onEvent(val('air', 'temperature', 1, 20, 3));
    streams[0]!.onEvent(snap(2));
  });
  expect(screen.getByText(/Some values may be missing/)).toBeTruthy();
});

it('shows each asset with its value and age, counts by state, and opens its card', async () => {
  jest.useFakeTimers();
  await render(<MapScreen />);
  await act(async () => {
    streams[0]!.onState?.('open');
    streams[0]!.onEvent(val('air', 'temperature', 1, 31.8, 8, { position: { lat: 40.0, lon: -74.0 } }));
    streams[0]!.onEvent(val('door', 'locked', 2, true, 7200, { unit: undefined }));
    streams[0]!.onEvent(snap(2));
    jest.advanceTimersByTime(300);
  });
  expect(screen.getByText('1 fresh')).toBeTruthy();
  expect(screen.getByText('1 offline')).toBeTruthy();
  expect(screen.getByTestId('plan-sensor.air')).toBeTruthy();
  expect(screen.queryByTestId('plan-sensor.door')).toBeNull(); // no position: list only
  expect(screen.getByText('1 without a position is only in the list.')).toBeTruthy();
  await fireEvent.press(screen.getByTestId('view-list'));
  expect(screen.getByText('31.8°C · 8 s')).toBeTruthy();
  await fireEvent.press(screen.getByTestId('row-sensor.door'));
  expect(screen.getByTestId('asset-card')).toBeTruthy();
  expect(screen.getAllByText(/2 h/).length).toBeGreaterThan(0);
  await fireEvent.press(screen.getByTestId('state-fresh'));
  expect(screen.queryByTestId('row-sensor.door')).toBeNull();
  jest.useRealTimers();
});

it('keeps the last map when the connection drops and says so', async () => {
  jest.useFakeTimers();
  await render(<MapScreen />);
  await act(async () => {
    streams[0]!.onState?.('open');
    streams[0]!.onEvent(val('air', 'temperature', 1, 20, 3, { position: { lat: 40.0, lon: -74.0 } }));
    streams[0]!.onEvent(snap(1));
    jest.advanceTimersByTime(300);
    streams[0]!.onState?.('retrying');
  });
  expect(screen.getByText(/Reconnecting\. This is the last map/)).toBeTruthy();
  expect(screen.getByTestId('plan-sensor.air')).toBeTruthy();
  await fireEvent.press(screen.getByTestId('view-list'));
  expect(screen.getByText('20°C · 3 s')).toBeTruthy();
  jest.useRealTimers();
});

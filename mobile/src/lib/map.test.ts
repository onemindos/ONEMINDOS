// SPDX-License-Identifier: Apache-2.0
import type { HubEvent } from '../api/types';
import { applyAssetEvent, boundsOf, countsByFreshness, formatValue, freshness, makeProjector, positionOf, shortAge, type AssetMap } from './map';

const NOW = Date.parse('2026-11-28T12:00:00Z');
const at = (s: number) => new Date(NOW - s * 1000).toISOString();

function value(id: string, field: string, revision: number, over: Record<string, unknown> = {}, cls = 'sensor'): HubEvent {
  return {
    schema: 'onemind.event/v1',
    id: `asset:${revision}`,
    type: 'asset.value',
    ts: at(0),
    subject: { asset_id: id, asset_class: cls, field },
    data: { revision, snapshot: false, datapoint: { schema: 'onemind.datapoint/v1', nats_subject: 'x', time: at(8), quality: 'live', source: { kind: 'node', id: 'n' }, value: 31.8, unit: 'Cel', ...over } },
  };
}

it('builds one asset from its fields and keeps the newest revision', () => {
  let m: AssetMap = {};
  m = applyAssetEvent(m, value('air', 'temperature', 5));
  m = applyAssetEvent(m, value('air', 'humidity', 6, { value: 60, unit: '%' }));
  m = applyAssetEvent(m, value('air', 'temperature', 4, { value: 1 })); // late, older
  expect(Object.keys(m)).toEqual(['sensor.air']);
  expect(formatValue(m['sensor.air']!.fields.temperature!)).toBe('31.8°C');
  expect(formatValue(m['sensor.air']!.fields.humidity!)).toBe('60%');
});

it('drops a field and then the asset on asset.removed', () => {
  let m = applyAssetEvent({}, value('air', 'temperature', 5));
  const gone: HubEvent = { ...value('air', 'temperature', 6), type: 'asset.removed', data: { revision: 6 } };
  m = applyAssetEvent(m, gone);
  expect(m).toEqual({});
});

it('ignores events that are not well-formed asset values', () => {
  const m: AssetMap = {};
  expect(applyAssetEvent(m, { ...value('a', 'f', 1), type: 'action.created' })).toBe(m);
  expect(applyAssetEvent(m, { ...value('a', 'f', 1), subject: {} })).toBe(m);
  expect(applyAssetEvent(m, value('a', 'f', 1, { quality: 'bogus' }))).toBe(m);
});

it('is fresh, stale or offline by age, and a source that says stale or unknown is never fresh', () => {
  const mk = (age: number, q = 'live') => applyAssetEvent({}, value('a', 'f', 1, { time: at(age), quality: q }))['sensor.a']!;
  expect(freshness(mk(8), NOW)).toBe('fresh');
  expect(freshness(mk(45), NOW)).toBe('stale');
  expect(freshness(mk(7200), NOW)).toBe('offline');
  expect(freshness(mk(1, 'stale'), NOW)).toBe('stale');
  expect(freshness(mk(1, 'unknown'), NOW)).toBe('offline');
  expect(countsByFreshness([mk(8), mk(45), mk(7200)], NOW)).toEqual({ fresh: 1, stale: 1, offline: 1 });
});

it('prints ages the way the design does', () => {
  expect([8, 180, 7200, 172800].map(shortAge)).toEqual(['8 s', '3 min', '2 h', '2 d']);
  expect(shortAge(null)).toBe('age unknown');
});

it('takes the position from the newest field that has one and projects inside the plan', () => {
  let m = applyAssetEvent({}, value('cam', 'image', 1, { position: { lat: 40.0, lon: -74.0 } }, 'camera'));
  m = applyAssetEvent(m, value('cam', 'online', 2, { position: { lat: 40.001, lon: -74.001 } }, 'camera'));
  const p = positionOf(m['camera.cam']!)!;
  expect(p).toEqual({ lat: 40.001, lon: -74.001 });
  const b = boundsOf([p, { lat: 40.0, lon: -74.0 }])!;
  const proj = makeProjector(b, 300, 300);
  const xy = proj(p);
  expect(xy.x).toBeGreaterThanOrEqual(0);
  expect(xy.x).toBeLessThanOrEqual(300);
  expect(xy.y).toBeGreaterThanOrEqual(0);
  expect(makeProjector(boundsOf([p])!, 300, 300)(p).x).toBeCloseTo(150); // a single point is centred
});

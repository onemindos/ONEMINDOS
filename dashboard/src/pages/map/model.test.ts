// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import type { MachineRecord, NodeRecord } from '../../api/types';
import { applyAssetEvent, gridStep, labelHasAge, labelOf, mapItems, shortAge, siteFrame, valueText, type AssetValue, type GeoSite } from './model';

const NOW = Date.parse('2026-11-28T12:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
// A site 40 m across: local x is metres east, y metres north of the first anchor (cos 45° ≈ 0.7071).
const LAT = 45, LON = 10;
const at = (x: number, y: number) => ({ x, y, lat: LAT + y / 110_574, lon: LON + x / (111_320 * Math.cos((LAT * Math.PI) / 180)) });
const SITE: GeoSite = { id: 'home', name: 'Home', anchors: [at(0, 0), at(40, 0), at(0, 30)], floors: [{ id: 'ground', name: 'Ground' }], areas: [] };

const node = (id: string, role: 'hub' | 'node', lastSeen: string): NodeRecord => ({ node_id: id, hostname: id, role, last_seen: lastSeen, status: 'online', cpus: 4, mem_total_mb: 8192 } as NodeRecord);
const machine: MachineRecord = { name: 'lab-vm', node_id: 'hub', ram_mb: 2048, cpus: 2, disk_gb: 20, state: 'running', created_at: ago(9000), updated_at: ago(60) };
const value = (cls: string, id: string, field: string, dp: AssetValue['datapoint']): [string, AssetValue] => [`${cls}.${id}.${field}`, { asset_class: cls, asset_id: id, field, datapoint: dp }];

describe('siteFrame', () => {
  it('turns a WGS-84 position back into site metres (the inverse of core geo/sites.py project)', () => {
    const f = siteFrame(SITE.anchors)!;
    const p = at(12.5, 7.25);
    const local = f.toLocal(p.lat, p.lon);
    expect(local.x).toBeCloseTo(12.5, 1);
    expect(local.y).toBeCloseTo(7.25, 1);
  });

  it('places a site that crosses the 180° meridian in metres, not 360° apart', () => {
    const across = [{ x: 0, y: 0, lat: 0.001, lon: 179.9995 }, { x: 111, y: 0, lat: 0.001, lon: -179.9995 }, { x: 0, y: 111, lat: 0.002, lon: 179.9995 }];
    const f = siteFrame(across)!;
    const p = f.toLocal(0.0015, -179.99975);
    expect(p.x).toBeGreaterThan(70);
    expect(p.x).toBeLessThan(95);
    expect(p.y).toBeCloseTo(55.5, 0);
  });

  it('refuses anchors on one line, which cannot fix a plan to the earth', () => {
    expect(siteFrame([at(0, 0), at(10, 0), at(20, 0)])).toBeUndefined();
    expect(siteFrame([at(0, 0), at(10, 0)])).toBeUndefined();
  });
});

describe('asset events', () => {
  it('keeps the latest value per key and drops removed keys', () => {
    const m = new Map<string, AssetValue>();
    const subject = { asset_class: 'sensor', asset_id: 'vent', field: 'temp' };
    expect(applyAssetEvent(m, { type: 'asset.value', subject, data: { datapoint: { value: 1, unit: 'Cel', time: ago(1) } } })).toBe(true);
    applyAssetEvent(m, { type: 'asset.value', subject, data: { datapoint: { value: 2, unit: 'Cel', time: ago(0) } } });
    expect(m.get('sensor.vent.temp')?.datapoint.value).toBe(2);
    expect(applyAssetEvent(m, { type: 'node.status', subject })).toBe(false);
    applyAssetEvent(m, { type: 'asset.removed', subject, data: { revision: 3 } });
    expect(m.size).toBe(0);
  });
});

describe('mapItems', () => {
  const nodes = [node('hub', 'hub', ago(3)), node('garage-pi', 'node', ago(400))];
  const status = (n: NodeRecord) => (n.node_id === 'hub' ? 'online' as const : 'offline' as const);
  const assets = new Map([
    value('sensor', 'greenhouse-air', 'temp', { time: ago(8), value: 31.8, unit: 'Cel', quality: 'live', position: at(10, 5) }),
    value('door', 'front', 'state', { time: ago(40), value: 'locked', quality: 'live', pose: { frame: 'ground', x: 2, y: 3 } }),
    value('sensor', 'bed-3', 'soil', { time: ago(19 * 60), value: 22, unit: '%', quality: 'live', position: at(20, 20) }),
    value('camera', 'far-away', 'state', { time: ago(5), value: 'on', quality: 'live', position: { lat: 46, lon: 11 } }),
    value('sensor', 'what-if', 'temp', { time: ago(2), value: 20, unit: 'Cel', quality: 'simulated' }),
    value('machine', 'lab-vm', 'cpu', { time: ago(4), value: 12, unit: '%', quality: 'live' }),
  ]);
  const items = mapItems({ now: NOW, nodes, nodeStatus: status, hubNodeId: 'hub', machines: [machine], assets, site: SITE });
  const byKey = (k: string) => items.find((i) => i.key === k)!;

  it('lists the box, its nodes, the machines on them and every asset once', () => {
    expect(items.map((i) => i.key).sort()).toEqual(['camera:far-away', 'door:front', 'machine:lab-vm', 'node:garage-pi', 'node:hub', 'sensor:bed-3', 'sensor:greenhouse-air', 'sensor:what-if']);
    expect(byKey('node:hub')).toMatchObject({ box: true, state: 'live', unplaced: expect.stringMatching(/not reported a position/) });
    expect(byKey('node:garage-pi').state).toBe('offline');
  });

  it('gives a machine its node\'s freshness and folds in the machine\'s own asset values', () => {
    const m = byKey('machine:lab-vm');
    expect(m).toMatchObject({ kind: 'machine', state: 'live', value: 'running', node: 'hub', link: '/machines' });
    expect(m.fields.map((f) => f.field)).toContain('cpu');
    const orphan = mapItems({ now: NOW, nodes: [], nodeStatus: status, machines: [machine], assets: new Map() })[0];
    expect(orphan?.state).toBe('unknown');
  });

  it('places assets only from a pose in this site or a position its anchors can fix', () => {
    expect(byKey('sensor:greenhouse-air').place).toMatchObject({ frame: 'home' });
    expect(byKey('sensor:greenhouse-air').place!.x).toBeCloseTo(10, 0);
    expect(byKey('door:front').place).toEqual({ x: 2, y: 3, frame: 'ground' });
    expect(byKey('camera:far-away')).toMatchObject({ place: undefined, unplaced: 'Its position is outside this place.' });
    expect(byKey('sensor:what-if')).toMatchObject({ place: undefined, simulated: true });
    const noSite = mapItems({ now: NOW, nodes: [], nodeStatus: status, machines: [], assets });
    expect(noSite.every((i) => !i.place)).toBe(true);
  });

  it('ages asset values: fresh under 2 min, stale after, offline after 15 min', () => {
    expect(byKey('sensor:greenhouse-air').state).toBe('live');
    expect(byKey('door:front').state).toBe('live');
    expect(byKey('sensor:bed-3').state).toBe('offline');
    const stale = mapItems({ now: NOW, nodes: [], nodeStatus: status, machines: [], assets: new Map([value('sensor', 's', 'v', { time: ago(300), value: 1, unit: 'Cel', quality: 'live' })]) });
    expect(stale[0]?.state).toBe('stale');
    const flagged = mapItems({ now: NOW, nodes: [], nodeStatus: status, machines: [], assets: new Map([value('sensor', 's', 'v', { time: ago(1), value: 1, unit: 'Cel', quality: 'stale' })]) });
    expect(flagged[0]?.state).toBe('stale');
  });

  it('prints an age on every label that shows a value (the om.js lint)', () => {
    for (const it of items) expect(labelHasAge(labelOf(it)), labelOf(it)).toBe(true);
    expect(labelOf(byKey('sensor:greenhouse-air'))).toBe('greenhouse-air · 31.8 °C · 8 s');
    expect(labelOf(byKey('node:garage-pi'))).toBe('garage-pi · off 6 min');
    expect(labelHasAge('Vent · 15 %')).toBe(false);
    const stale = mapItems({ now: NOW, nodes: [], nodeStatus: status, machines: [], assets: new Map([value('door', 'back', 'state', { time: ago(300), value: 'open', quality: 'live' })]) });
    expect(labelOf(stale[0]!)).toBe('back · open · stale 5 min');
  });
});

describe('formatting', () => {
  it('writes ages and values in a few words', () => {
    expect([shortAge(2), shortAge(8), shortAge(180), shortAge(7200), shortAge(200_000), shortAge(null)]).toEqual(['now', '8 s', '3 min', '2 h', '2 d', 'no time']);
    expect(valueText({ value: 15, unit: '%' })).toBe('15 %');
    expect(valueText({ value: true })).toBe('on');
    expect(valueText({ value: { state: 'open' } })).toBe('open');
    expect(valueText({ value: { a: [1] } })).toBe('data');
    expect(gridStep(40)).toBe(5);
    expect(gridStep(400)).toBe(50);
  });
});

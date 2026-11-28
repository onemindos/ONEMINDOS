// SPDX-License-Identifier: Apache-2.0
// Map v0 (#653, #1025 "machines on the map"): what the Map draws, as plain functions so the rules are tested
// without a browser. Everything comes from the gateway: nodes (GET /v1/nodes), machines (GET /v1/machines),
// sites (GET /v1/sites) and asset values (GET /v1/events?types=asset.*). Nothing here invents a position:
// an item is on the plan only when the gateway reported a pose in this site's frame, or a WGS-84 position
// the site's surveyed anchors can place. Everything else waits on the "not on the plan yet" shelf.
import { freshness, type Freshness, type FreshnessLimits } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import type { MachineRecord, NodeRecord, NodeStatus } from '../../api/types';

export type GeoSite = components['schemas']['GeoSite'];
type Anchor = components['schemas']['Anchor'];

/** Asset values age like moving assets in the design (DESIGN.md, 02g): stale after 2 min, offline after 15. */
export const ASSET_LIMITS: FreshnessLimits = { staleAfter: 120, offlineAfter: 900 };
/** A WGS-84 position further than this from the site's anchors is somewhere else, not on this plan. */
export const SITE_REACH_M = 5_000;

/** The parts of an onemind.datapoint/v1 the map reads (sdk/schema/onemind.datapoint.schema.json). */
export interface Datapoint {
  time?: string;
  value?: unknown;
  unit?: string;
  quality?: 'live' | 'stale' | 'unknown' | 'simulated' | string;
  position?: { lat: number; lon: number };
  pose?: { frame: string; x: number; y: number };
}

/** One current asset value, keyed `<asset_class>.<asset_id>.<field>` like the gateway's asset-state bucket. */
export interface AssetValue { asset_class: string; asset_id: string; field: string; datapoint: Datapoint }
export type AssetValues = ReadonlyMap<string, AssetValue>;

interface StreamEvent { type: string; subject?: Record<string, unknown>; data?: Record<string, unknown> }

/** Apply one event to the current values: asset.value replaces a key (latest wins), asset.removed drops it. */
export function applyAssetEvent(values: Map<string, AssetValue>, e: StreamEvent): boolean {
  if (e.type !== 'asset.value' && e.type !== 'asset.removed') return false;
  const s = e.subject ?? {};
  const [cls, id, field] = [s.asset_class, s.asset_id, s.field];
  if (typeof cls !== 'string' || typeof id !== 'string' || typeof field !== 'string') return false;
  const key = `${cls}.${id}.${field}`;
  if (e.type === 'asset.removed') return values.delete(key);
  const dp = e.data?.datapoint;
  if (!dp || typeof dp !== 'object') return false;
  values.set(key, { asset_class: cls, asset_id: id, field, datapoint: dp as Datapoint });
  return true;
}

/** "now", "8 s", "3 min", "2 h", "4 d": the age printed on every value label (DESIGN.md rule 1). */
export function shortAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return 'no time';
  if (seconds < 5) return 'now';
  if (seconds < 60) return `${Math.floor(seconds)} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h`;
  return `${Math.floor(seconds / 86_400)} d`;
}

export function ageOf(iso: string | undefined, now: number): number | null {
  const t = iso ? Date.parse(iso) : Number.NaN;
  return Number.isNaN(t) ? null : Math.max(0, Math.floor((now - t) / 1000));
}

const UNIT: Record<string, string> = { Cel: '°C', '%': '%', 'km/h': 'km/h', 'm/s': 'm/s' };

/** A datapoint value in a few words: "31.8 °C", "on", "locked"; never a raw object dump. */
export function valueText(dp: Datapoint): string {
  const v = dp.value;
  if (typeof v === 'number') {
    const unit = dp.unit ? UNIT[dp.unit] ?? dp.unit : '';
    const n = Number.isInteger(v) ? String(v) : v.toFixed(1);
    return unit === '%' ? `${n} %` : unit ? `${n} ${unit}` : n;
  }
  if (typeof v === 'boolean') return v ? 'on' : 'off';
  if (typeof v === 'string') return v.length > 40 ? `${v.slice(0, 39)}…` : v;
  if (v && typeof v === 'object') {
    const inner = (v as Record<string, unknown>).state ?? (v as Record<string, unknown>).value;
    if (typeof inner === 'string' || typeof inner === 'number' || typeof inner === 'boolean') return valueText({ ...dp, value: inner });
    return 'data';
  }
  return 'no value';
}

/** Local metres from WGS-84 for one site: the inverse of core/onemind_core/geo/sites.py `project`. */
export interface SiteFrame { toLocal: (lat: number, lon: number) => { x: number; y: number } }

/**
 * Least-squares affine fit from the anchors' (lat, lon) to their (x, y), over a local east/north tangent plane
 * so the numbers stay well conditioned. Undefined when the anchors do not span two dimensions (a line).
 */
export function siteFrame(anchors: readonly Anchor[]): SiteFrame | undefined {
  const n = anchors.length;
  if (n < 3) return undefined;
  // Unwrap longitudes next to the first anchor, so a site across the 180° meridian is not 360° wide.
  const ref = anchors[0]!.lon;
  const unwrap = (lon: number) => lon - 360 * Math.round((lon - ref) / 360);
  const lat0 = anchors.reduce((s, a) => s + a.lat, 0) / n;
  const lon0 = anchors.reduce((s, a) => s + unwrap(a.lon), 0) / n;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const en = (lat: number, lon: number) => ({ e: (unwrap(lon) - lon0) * k * 111_320, n: (lat - lat0) * 110_574 });
  const pts = anchors.map((a) => ({ ...en(a.lat, a.lon), x: a.x, y: a.y }));
  const me = pts.reduce((s, p) => s + p.e, 0) / n;
  const mn = pts.reduce((s, p) => s + p.n, 0) / n;
  const mx = pts.reduce((s, p) => s + p.x, 0) / n;
  const my = pts.reduce((s, p) => s + p.y, 0) / n;
  let ee = 0, eN = 0, nn = 0, ex = 0, nx = 0, ey = 0, ny = 0;
  for (const p of pts) {
    const de = p.e - me, dn = p.n - mn, dx = p.x - mx, dy = p.y - my;
    ee += de * de; eN += de * dn; nn += dn * dn; ex += de * dx; nx += dn * dx; ey += de * dy; ny += dn * dy;
  }
  const det = ee * nn - eN * eN;
  // The same degeneracy test as core geo/sites.py project (relative 1e-12), here on the east/north side.
  if (!(det > 1e-12 * (ee + nn) ** 2)) return undefined;
  const solve = (be: number, bn: number) => ({ a: (be * nn - bn * eN) / det, b: (bn * ee - be * eN) / det });
  const fx = solve(ex, nx), fy = solve(ey, ny);
  return {
    toLocal: (lat, lon) => {
      const p = en(lat, lon);
      const de = p.e - me, dn = p.n - mn;
      return { x: mx + fx.a * de + fx.b * dn, y: my + fy.a * de + fy.b * dn };
    },
  };
}

export type ItemKind = 'node' | 'machine' | 'asset';

export interface ItemField { field: string; value: string; age: number | null; quality?: string }

export interface MapItem {
  key: string;
  kind: ItemKind;
  /** Layer: the asset class ("node", "machine", "sensor", ...). */
  layer: string;
  id: string;
  name: string;
  state: Freshness;
  simulated: boolean;
  /** The headline value ("running", "31.8 °C"); absent when the item reports no value. */
  value?: string;
  /** Seconds since the newest report; null when no readable time. */
  age: number | null;
  fields: ItemField[];
  /** The node a machine runs on. */
  node?: string;
  /** The box itself (the hub node). */
  box?: boolean;
  /** Metres in the site frame and the frame it was reported in (the site or one of its floors). */
  place?: { x: number; y: number; frame: string };
  /** Why it is not on this plan, in plain words. */
  unplaced?: string;
  link?: string;
}

const RANK: Record<Freshness, number> = { live: 0, stale: 1, unknown: 2, offline: 3 };
const worse = (a: Freshness, b: Freshness): Freshness => (RANK[a] >= RANK[b] ? a : b);
const fromNode = (s: NodeStatus): Freshness => (s === 'online' ? 'live' : s);

function datapointState(dp: Datapoint, now: number): Freshness {
  let s = freshness(ageOf(dp.time, now) ?? Number.NaN, ASSET_LIMITS);
  if (dp.quality === 'stale') s = worse(s, 'stale');
  if (dp.quality === 'unknown') s = worse(s, 'unknown');
  return s;
}

interface Placement { site?: GeoSite; frame?: SiteFrame }

/** Where a datapoint puts its asset on this site, or why it does not. */
function placeOf(dp: Datapoint, at: Placement): Pick<MapItem, 'place' | 'unplaced'> {
  const site = at.site;
  if (dp.pose && site) {
    const frames = new Set([site.id, ...(site.floors ?? []).map((f) => f.id)]);
    if (frames.has(dp.pose.frame)) return { place: { x: dp.pose.x, y: dp.pose.y, frame: dp.pose.frame } };
  }
  if (dp.position && at.frame && site) {
    const p = at.frame.toLocal(dp.position.lat, dp.position.lon);
    const anchors = site.anchors;
    const cx = anchors.reduce((s, a) => s + a.x, 0) / anchors.length;
    const cy = anchors.reduce((s, a) => s + a.y, 0) / anchors.length;
    if (Number.isFinite(p.x) && Number.isFinite(p.y) && Math.hypot(p.x - cx, p.y - cy) <= SITE_REACH_M) return { place: { ...p, frame: site.id } };
    return { unplaced: 'Its position is outside this place.' };
  }
  if (dp.pose) return { unplaced: `It reports a position on another plan (${dp.pose.frame}).` };
  if (dp.position) return { unplaced: site ? 'This place has no usable surveyed points to fix it to the earth.' : 'No place is drawn yet.' };
  return {};
}

const NO_POSITION = 'It has not reported a position yet.';

function assetGroups(values: AssetValues): Map<string, AssetValue[]> {
  const out = new Map<string, AssetValue[]>();
  for (const v of values.values()) {
    const k = `${v.asset_class}:${v.asset_id}`;
    out.set(k, [...(out.get(k) ?? []), v]);
  }
  return out;
}

/** Fold one asset's field values into the item: newest time, worst state, a position if any field has one. */
function withAsset(base: MapItem, vals: AssetValue[], now: number, at: Placement): MapItem {
  const sorted = [...vals].sort((a, b) => (Date.parse(b.datapoint.time ?? '') || 0) - (Date.parse(a.datapoint.time ?? '') || 0));
  const fields: ItemField[] = sorted.map((v) => ({ field: v.field, value: valueText(v.datapoint), age: ageOf(v.datapoint.time, now), quality: v.datapoint.quality }));
  const newest = sorted[0];
  if (!newest) return base;
  const head = sorted.find((v) => v.field === 'state') ?? newest;
  const placed = sorted.map((v) => placeOf(v.datapoint, at));
  const where = placed.find((p) => p.place) ?? placed.find((p) => p.unplaced) ?? {};
  return {
    ...base,
    // An asset is as fresh as its newest report; a node or machine keeps the node's heartbeat verdict.
    state: base.kind === 'asset' ? datapointState(newest.datapoint, now) : base.state,
    simulated: sorted.some((v) => v.datapoint.quality === 'simulated'),
    value: base.value ?? valueText(head.datapoint),
    age: base.kind === 'asset' ? ageOf(newest.datapoint.time, now) : base.age,
    fields: [...base.fields, ...fields],
    place: where.place,
    unplaced: where.place ? undefined : where.unplaced ?? base.unplaced,
  };
}

export interface MapInputs {
  now: number;
  nodes: readonly NodeRecord[];
  nodeStatus: (n: NodeRecord) => NodeStatus;
  hubNodeId?: string;
  machines: readonly MachineRecord[];
  assets: AssetValues;
  site?: GeoSite;
}

/** Every item the Map knows about: the box and its nodes, the machines on them, and each asset with values. */
export function mapItems(i: MapInputs): MapItem[] {
  const at: Placement = { site: i.site, frame: i.site ? siteFrame(i.site.anchors) : undefined };
  const groups = assetGroups(i.assets);
  const take = (cls: string, id: string) => {
    const k = `${cls}:${id}`;
    const v = groups.get(k);
    groups.delete(k);
    return v;
  };
  const items: MapItem[] = [];
  const nodeState = new Map<string, Freshness>();
  for (const n of i.nodes) {
    const state = fromNode(i.nodeStatus(n));
    nodeState.set(n.node_id, state);
    const box = n.node_id === i.hubNodeId || n.role === 'hub';
    const base: MapItem = {
      key: `node:${n.node_id}`, kind: 'node', layer: 'node', id: n.node_id, name: n.hostname || n.node_id, state, simulated: false,
      value: state === 'live' ? 'online' : state, age: ageOf(n.last_seen, i.now), box, unplaced: NO_POSITION, link: '/nodes',
      fields: [
        { field: 'role', value: box ? 'the box (hub)' : 'node', age: ageOf(n.last_seen, i.now) },
        ...(n.cpus ? [{ field: 'CPUs', value: String(n.cpus), age: ageOf(n.last_seen, i.now) }] : []),
        ...(n.mem_total_mb ? [{ field: 'memory', value: `${Math.round(n.mem_total_mb / 1024)} GB`, age: ageOf(n.last_seen, i.now) }] : []),
      ],
    };
    const vals = take('node', n.node_id);
    items.push(vals ? withAsset(base, vals, i.now, at) : base);
  }
  for (const m of i.machines) {
    // A machine is only as current as the node that reports it; with no node on record its state is unknown.
    const state = nodeState.get(m.node_id) ?? 'unknown';
    const host = i.nodes.find((n) => n.node_id === m.node_id);
    const base: MapItem = {
      key: `machine:${m.name}`, kind: 'machine', layer: 'machine', id: m.name, name: m.name, state, simulated: false,
      value: m.state, age: host ? ageOf(host.last_seen, i.now) : null, node: m.node_id, unplaced: NO_POSITION, link: '/machines',
      fields: [
        { field: 'runs on', value: host?.hostname || m.node_id, age: host ? ageOf(host.last_seen, i.now) : null },
        { field: 'size', value: `${m.cpus} CPU · ${Math.round(m.ram_mb / 1024 * 10) / 10} GB RAM · ${m.disk_gb} GB disk`, age: host ? ageOf(host.last_seen, i.now) : null },
      ],
    };
    const vals = take('machine', m.name);
    items.push(vals ? withAsset(base, vals, i.now, at) : base);
  }
  for (const [k, vals] of groups) {
    if (!vals[0]) continue;
    const { asset_class: cls, asset_id: id } = vals[0];
    const base: MapItem = { key: k, kind: 'asset', layer: cls, id, name: id, state: 'unknown', simulated: false, age: null, fields: [], unplaced: NO_POSITION };
    items.push(withAsset(base, vals, i.now, at));
  }
  return items;
}

/** The text on a marker: name, value and age. A value never appears without its age. */
export function labelOf(item: MapItem): string {
  const age = shortAge(item.age);
  // The state is a word on the label too, not only a shape or colour: "off", "stale", "unknown"; fresh needs none.
  if (item.state === 'offline') return `${item.name} · off ${age}`;
  const when = item.state === 'stale' ? `stale ${age}` : item.state === 'unknown' ? `unknown · ${age}` : age;
  return item.value ? `${item.name} · ${item.value} · ${when}` : `${item.name} · ${when}`;
}

/** The om.js lint (design-v2 final/lib/om.js): a label that shows a value must also show an age. */
export const VALUE_RE = /\d|%|°|km\/h|\b(locked|unlocked|open|closed|armed|disarmed|on|off|idle|running|stopped)\b/i;
export const AGE_RE = /\b\d+(\.\d+)?\s?(s|min|h|d)\b|\bnow\b|\blive\b|\bno time\b/i;
export const labelHasAge = (text: string) => !VALUE_RE.test(text) || AGE_RE.test(text);

export const LAYER_NAMES: Record<string, string> = { node: 'Box and nodes', machine: 'Machines' };
export const layerName = (layer: string) => LAYER_NAMES[layer] ?? `${layer.charAt(0).toUpperCase()}${layer.slice(1)}`;

export type StateCounts = Record<Freshness, number>;
export function counts(items: readonly MapItem[]): StateCounts {
  const out: StateCounts = { live: 0, stale: 0, offline: 0, unknown: 0 };
  for (const it of items) out[it.state] += 1;
  return out;
}

/** A tidy grid step (1, 2 or 5 × 10^n metres) that gives about `lines` lines across `span`. */
export function gridStep(span: number, lines = 8): number {
  const raw = Math.max(span, 1) / lines;
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? 10 * p;
}

export interface Bounds { minX: number; minY: number; maxX: number; maxY: number }

/** The plan's extent in metres: the anchors and every placed item, padded, at least 10 m across. */
export function planBounds(site: GeoSite | undefined, items: readonly MapItem[]): Bounds {
  const xs: number[] = [], ys: number[] = [];
  for (const a of site?.anchors ?? []) { xs.push(a.x); ys.push(a.y); }
  for (const it of items) if (it.place) { xs.push(it.place.x); ys.push(it.place.y); }
  if (!xs.length) return { minX: 0, minY: 0, maxX: 10, maxY: 10 };
  let [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const span = Math.max(maxX - minX, maxY - minY, 10);
  const pad = span * 0.12;
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  minX = cx - span / 2 - pad; maxX = cx + span / 2 + pad; minY = cy - span / 2 - pad; maxY = cy + span / 2 + pad;
  return { minX, minY, maxX, maxY };
}

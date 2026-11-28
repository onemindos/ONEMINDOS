// SPDX-License-Identifier: Apache-2.0
// Phone Map tab (#656): the box's assets as one tile each, built from the asset values on `GET /v1/events?types=asset.*`
// (#606; subject {asset_id, asset_class, field}, data.datapoint = onemind.datapoint/v1). Pure functions, tested directly.
// Rule from the Atlas design (docs/design/atlas-phone/README.md): no value without its age; status by shape and word.
import type { HubEvent } from '../api/types';
import { OFFLINE_AFTER_S, STALE_AFTER_S } from './time';

export interface AssetField {
  value: unknown;
  unit?: string;
  /** When the value was observed (the datapoint's own time, not when the phone heard it). */
  time: string;
  quality: 'live' | 'stale' | 'unknown' | 'simulated';
  revision: number;
  position?: { lat: number; lon: number };
}

export interface Asset {
  key: string;
  id: string;
  cls: string;
  fields: Record<string, AssetField>;
}

export type AssetMap = Record<string, Asset>;
export type Freshness = 'fresh' | 'stale' | 'offline';

const QUALITIES = new Set(['live', 'stale', 'unknown', 'simulated']);

const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** Fold one event into the map. Anything that is not a well-formed asset event leaves it untouched. */
export function applyAssetEvent(map: AssetMap, e: HubEvent): AssetMap {
  if (e.type !== 'asset.value' && e.type !== 'asset.removed') return map;
  const id = e.subject?.asset_id;
  const cls = e.subject?.asset_class;
  const field = e.subject?.field;
  if (!id || !cls || !field) return map;
  const key = `${cls}.${id}`;
  const cur = map[key];
  if (e.type === 'asset.removed') {
    if (!cur?.fields[field]) return map;
    const { [field]: _gone, ...rest } = cur.fields;
    const { [key]: _asset, ...others } = map;
    return Object.keys(rest).length ? { ...others, [key]: { ...cur, fields: rest } } : others;
  }
  const dp = (e.data?.datapoint ?? undefined) as Record<string, unknown> | undefined;
  const revision = num(e.data?.revision) ? (e.data.revision as number) : 0;
  if (!dp || typeof dp.time !== 'string' || !QUALITIES.has(String(dp.quality))) return map;
  if (cur?.fields[field] && cur.fields[field].revision > revision) return map; // an older value arriving late
  const p = dp.position as { lat?: unknown; lon?: unknown } | undefined;
  const next: AssetField = {
    value: dp.value,
    unit: typeof dp.unit === 'string' ? dp.unit : undefined,
    time: dp.time,
    quality: dp.quality as AssetField['quality'],
    revision,
    position: p && num(p.lat) && num(p.lon) ? { lat: p.lat, lon: p.lon } : undefined,
  };
  return { ...map, [key]: { key, id, cls, fields: { ...(cur?.fields ?? {}), [field]: next } } };
}

export function ageSeconds(time: string, now: number): number | null {
  const t = Date.parse(time);
  return Number.isNaN(t) ? null : Math.max(0, Math.floor((now - t) / 1000));
}

/** "8 s", "3 min", "2 h", "4 d": the short form the design prints on every label. */
export function shortAge(s: number | null): string {
  if (s === null) return 'age unknown';
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h`;
  return `${Math.floor(s / 86400)} d`;
}

/** The newest field decides how fresh the asset is; a source that says stale or unknown is never shown as fresh. */
export function newestField(a: Asset): [string, AssetField] | undefined {
  let best: [string, AssetField] | undefined;
  for (const [name, f] of Object.entries(a.fields)) {
    if (!best || Date.parse(f.time) > Date.parse(best[1].time)) best = [name, f];
  }
  return best;
}

export function freshness(a: Asset, now: number): Freshness {
  const n = newestField(a);
  if (!n) return 'offline';
  const age = ageSeconds(n[1].time, now);
  if (age === null || n[1].quality === 'unknown' || age >= OFFLINE_AFTER_S) return 'offline';
  return n[1].quality === 'stale' || age >= STALE_AFTER_S ? 'stale' : 'fresh';
}

export const FRESH_WORD: Record<Freshness, string> = { fresh: 'fresh', stale: 'stale', offline: 'offline' };

export function formatValue(f: AssetField): string {
  const v = f.value;
  if (v === null || v === undefined) return 'no value';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'object') return 'details';
  const u = f.unit === 'Cel' ? '°C' : f.unit === 'By' ? 'B' : (f.unit ?? '');
  return `${String(v)}${u ? (u === '%' || u === '°C' ? u : ` ${u}`) : ''}`;
}

/** Where the asset is: the newest field that carries a position. */
export function positionOf(a: Asset): { lat: number; lon: number } | undefined {
  let best: AssetField | undefined;
  for (const f of Object.values(a.fields)) if (f.position && (!best || f.revision > best.revision)) best = f;
  return best?.position;
}

export function sortedAssets(map: AssetMap): Asset[] {
  return Object.values(map).sort((a, b) => a.cls.localeCompare(b.cls) || a.id.localeCompare(b.id));
}

export function countsByFreshness(list: Asset[], now: number): Record<Freshness, number> {
  const c: Record<Freshness, number> = { fresh: 0, stale: 0, offline: 0 };
  for (const a of list) c[freshness(a, now)]++;
  return c;
}

export interface Bounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
}

export function boundsOf(points: Array<{ lat: number; lon: number }>): Bounds | undefined {
  if (!points.length) return undefined;
  return {
    minLat: Math.min(...points.map((p) => p.lat)),
    maxLat: Math.max(...points.map((p) => p.lat)),
    minLon: Math.min(...points.map((p) => p.lon)),
    maxLon: Math.max(...points.map((p) => p.lon)),
  };
}

/**
 * Plan projection: local equirectangular (longitude scaled by cos(lat)), fitted into width x height with a margin.
 * A single point or a very small area is centred, never stretched to the edges.
 */
export function makeProjector(b: Bounds, width: number, height: number, margin = 36) {
  const k = Math.cos((((b.minLat + b.maxLat) / 2) * Math.PI) / 180) || 1;
  const w = Math.max((b.maxLon - b.minLon) * k, 1e-5);
  const h = Math.max(b.maxLat - b.minLat, 1e-5);
  const scale = Math.min((width - 2 * margin) / w, (height - 2 * margin) / h);
  const midLon = (b.minLon + b.maxLon) / 2;
  const midLat = (b.minLat + b.maxLat) / 2;
  return (p: { lat: number; lon: number }) => ({ x: width / 2 + (p.lon - midLon) * k * scale, y: height / 2 + (midLat - p.lat) * scale });
}

export function inBounds(p: { lat: number; lon: number }, b: Bounds, pad = 0): boolean {
  return p.lat >= b.minLat - pad && p.lat <= b.maxLat + pad && p.lon >= b.minLon - pad && p.lon <= b.maxLon + pad;
}

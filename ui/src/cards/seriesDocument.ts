// SPDX-License-Identifier: Apache-2.0
/** A host-rendered card binds to one known query. Its document contains no presentation code. */
export const SERIES_METRICS = {
  cpu_pct: { label: 'Processor', unit: '%' },
  mem_used_mb: { label: 'Memory used', unit: ' MiB' },
  temp_c: { label: 'Temperature', unit: ' °C' },
} as const;

export type SeriesMetric = keyof typeof SERIES_METRICS;
export const SERIES_INTERVAL_S = 60;
export const SERIES_POINTS = 60;

export interface SeriesCardDocument {
  version: 1;
  kind: 'series';
  series: { nodeId: string; metric: SeriesMetric };
}

export function isSeriesNodeId(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(value);
}

function hasOnlyKeys(value: unknown, keys: string[]): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const owned = Object.keys(value);
  return owned.length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

export function parseSeriesCard(value: unknown): SeriesCardDocument | undefined {
  if (!hasOnlyKeys(value, ['version', 'kind', 'series']) || value.version !== 1 || value.kind !== 'series') return;
  const series = value.series;
  if (!hasOnlyKeys(series, ['nodeId', 'metric']) || !isSeriesNodeId(series.nodeId) || typeof series.metric !== 'string'
    || !Object.hasOwn(SERIES_METRICS, series.metric)) return;
  return { version: 1, kind: 'series', series: { nodeId: series.nodeId, metric: series.metric as SeriesMetric } };
}

// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { SeriesCard } from './SeriesCard';
import { parseSeriesCard, SERIES_INTERVAL_S, type SeriesCardDocument } from './seriesDocument';

const series: SeriesCardDocument = { version: 1, kind: 'series', series: { nodeId: 'node-1', metric: 'cpu_pct' } };

it('accepts the fixed series binding and refuses unknown fields and executable or URL values', () => {
  expect(parseSeriesCard(JSON.parse(JSON.stringify(series)))).toEqual(series);
  for (const invalid of [
    { ...series, url: 'https://example.invalid/history' },
    { ...series, script: 'alert(1)' },
    { ...series, series: { ...series.series, url: 'https://example.invalid/history' } },
    { ...series, series: { ...series.series, nodeId: 'https://example.invalid/history' } },
    { ...series, series: { ...series.series, metric: 'javascript:alert(1)' } },
    { ...series, series: { ...series.series, metric: 'constructor' } },
    { ...series, kind: 'plugin' },
  ]) expect(parseSeriesCard(invalid)).toBeUndefined();
});

it('marks readings stale as soon as two intervals have elapsed', () => {
  const at = '2026-11-01T10:00:00Z';
  const samples = [{ at, value: 25 }];
  const limit = Date.parse(at) + 2 * SERIES_INTERVAL_S * 1000;
  const view = render(<SeriesCard document={series} data={{ state: 'loaded', samples }} now={limit - 1} />);
  expect(screen.getByText('Online')).toBeVisible();
  view.rerender(<SeriesCard document={series} data={{ state: 'loaded', samples }} now={limit} />);
  expect(screen.getByText('Stale')).toBeVisible();
  expect(screen.getByRole('cell', { name: '25%' })).toBeVisible();
});

it('shows why readings are unavailable without drawing a chart or a value', () => {
  render(<SeriesCard document={series} data={{ state: 'denied' }} now={Date.now()} />);
  expect(screen.getByRole('status')).toHaveTextContent('Your account does not have access to this history.');
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

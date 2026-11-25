// SPDX-License-Identifier: Apache-2.0
import { Card } from '../components/Card';
import { FreshnessPill } from '../components/StatusPill';
import { Table } from '../components/Table';
import { SERIES_INTERVAL_S, SERIES_METRICS, type SeriesCardDocument } from './seriesDocument';

export interface SeriesReading {
  at: string;
  value: number;
}

export type SeriesCardData =
  | { state: 'loading' | 'denied' | 'unavailable' }
  | { state: 'loaded'; samples: SeriesReading[]; refreshFailed?: boolean };

const EMPTY = {
  loading: 'Loading history…',
  denied: 'Your account does not have access to this history.',
  unavailable: 'The gateway could not load this history.',
} as const;

export function SeriesCard({ document, data, now }: { document: SeriesCardDocument; data: SeriesCardData; now: number }) {
  const { label, unit } = SERIES_METRICS[document.series.metric];
  if (data.state !== 'loaded') return <Card title={label}><p role="status">{EMPTY[data.state]}</p></Card>;

  const samples = data.samples.filter((point) => Number.isFinite(point.value) && Number.isFinite(Date.parse(point.at)))
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  const latest = samples[0];
  if (!latest) {
    return <Card title={label}><p role="status">{data.refreshFailed ? EMPTY.unavailable : 'No readings in the last hour.'}</p></Card>;
  }

  const stale = !!data.refreshFailed || now - Date.parse(latest.at) >= 2 * SERIES_INTERVAL_S * 1000;
  const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
  const format = (value: number) => number.format(value) + unit;
  return (
    <Card title={label} variant={stale ? 'stale' : 'default'} aside={<FreshnessPill state={stale ? 'stale' : 'live'} />}>
      <p>Latest reading: <strong>{format(latest.value)}</strong></p>
      {data.refreshFailed && <p role="status">{EMPTY.unavailable} Showing the last successful reading.</p>}
      <Table
        caption={`${label} readings in the last hour`}
        columns={[
          { key: 'time', header: 'Recorded at', render: ({ at }) => <time dateTime={at}>{new Date(at).toLocaleTimeString()}</time> },
          { key: 'reading', header: 'Reading', align: 'end', render: ({ value }) => format(value) },
        ]}
        rows={samples}
        rowKey={(point) => point.at}
      />
    </Card>
  );
}

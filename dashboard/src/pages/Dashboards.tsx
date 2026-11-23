// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type operations } from '@onemind/sdk';
import {
  Button, PageHeader, SeriesCard, isSeriesNodeId, parseSeriesCard,
  SERIES_INTERVAL_S, SERIES_METRICS, SERIES_POINTS, type SeriesCardDocument, type SeriesCardData,
} from '@onemind/ui';
import { ApiError } from '../api/types';
import { useNow, usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load } from './parts';

type Query = operations['series.query']['parameters']['query'];
type Series = operations['series.query']['responses'][200]['content']['application/json'];

async function read<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (!(error instanceof OneMindError)) throw error;
    // Replace previous readings on revocation. A later outage must never reveal them again.
    if (error.status === 401 || error.status === 403) return null;
    throw new ApiError(error.status, 'unknown', error.message, error.reason);
  }
}

function HistoryCard({ client, document }: { client: OneMind; document: SeriesCardDocument }) {
  const res = usePoll(async () => {
    const query: Query = {
      node_id: document.series.nodeId,
      metric: document.series.metric,
      window_s: SERIES_INTERVAL_S * SERIES_POINTS,
      points: SERIES_POINTS,
    };
    const params = new URLSearchParams(Object.entries(query).map(([key, value]) => [key, String(value)]));
    return read(client.call<Series>({ method: 'GET', path: `/v1/series?${params}` }));
  }, SERIES_INTERVAL_S * 1000);
  const now = useNow();
  let data: SeriesCardData;
  if (res.data === null) data = { state: 'denied' };
  else if (res.data) data = { state: 'loaded', samples: res.data, refreshFailed: !!res.error };
  else data = { state: res.error ? 'unavailable' : 'loading' };

  return (
    <>
      <SeriesCard document={document} data={data} now={now} />
      <Button variant="ghost" onClick={() => void res.reload()}>Refresh history</Button>
    </>
  );
}

function LiveDashboards({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const nodes = usePoll(() => read(client.nodes.list()), SERIES_INTERVAL_S * 1000);
  const [nodeId, setNodeId] = useState('');
  const [metric, setMetric] = useState('cpu_pct');

  if (nodes.data === null) {
    return <p role="status">Your account does not have access to machine history.</p>;
  }
  return (
    <Load res={nodes} what="Loading machines">
      {(all) => {
        const available = (all ?? []).filter((node) => isSeriesNodeId(node.node_id));
        const selected = available.find((node) => node.node_id === nodeId) ?? available[0];
        if (!selected) return <p role="status">No machines have reported to this hub.</p>;

        const document = parseSeriesCard({ version: 1, kind: 'series', series: { nodeId: selected.node_id, metric } });
        return (
          <>
            <div className="dash-actions">
              <label>
                Machine{' '}
                <select value={selected.node_id} onChange={(event) => setNodeId(event.target.value)}>
                  {available.map((node) => <option key={node.node_id} value={node.node_id}>{node.hostname || node.node_id}</option>)}
                </select>
              </label>
              <label>
                Metric{' '}
                <select value={metric} onChange={(event) => setMetric(event.target.value)}>
                  {Object.entries(SERIES_METRICS).map(([id, { label }]) => <option key={id} value={id}>{label}</option>)}
                </select>
              </label>
            </div>
            {document && <HistoryCard key={`${document.series.nodeId}:${document.series.metric}`} client={client} document={document} />}
          </>
        );
      }}
    </Load>
  );
}

export function Dashboards() {
  const { token, person, mock } = useSignedIn();
  return (
    <div className="dash-stack">
      <PageHeader title="Dashboards" />
      {mock
        ? <p role="status">Connect to a hub to see machine history.</p>
        : <LiveDashboards key={person} token={token} />}
    </div>
  );
}

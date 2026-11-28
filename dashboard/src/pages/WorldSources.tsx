// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

type Bridge = components['schemas']['BridgeStatus'];
type Latest = components['schemas']['LatestValue'];
const denied = (error: ApiError | undefined) => error?.status === 401 || error?.status === 403;

function read<T>(sdk: OneMind, path: string) {
  return sdk.call<T>({ method: 'GET', path, redirect: 'error' }).catch((error: unknown) => {
    if (error instanceof OneMindError) throw new ApiError(error.status, error.status === 401 ? 'unauthenticated' : error.status === 403 ? 'permission_denied' : 'unknown', error.message);
    throw error;
  });
}
const object = (value: unknown) => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const displayTime = (value: string) => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : 'Unknown';

function attributedItem(row: Latest) {
  const payload = object(row.datapoint);
  const attribution = object(payload.licence).attribution;
  const value = object(payload.value);
  const headline = typeof value.headline === 'string' ? value.headline : value.title;
  return typeof attribution === 'string' && attribution.trim() && typeof headline === 'string' && headline.trim()
    ? { headline, attribution, asOf: typeof payload.time === 'string' ? payload.time : row.received_at } : undefined;
}

function SourceItems({ sdk, bridge }: { sdk: OneMind; bridge: Bridge }) {
  const feed = usePoll(() => read<Latest[]>(sdk, `/v1/bridges/${encodeURIComponent(bridge.id)}/latest`), 30_000);
  if (denied(feed.error)) return <p>Owner only</p>;
  if (!feed.data) return <p role="status">{feed.error ? 'Could not load source items.' : 'Checking for items…'}</p>;
  const entries = feed.data.flatMap((item) => {
    const content = attributedItem(item);
    return content ? [{ ...content, key: `${item.kind}/${item.name}/${item.id}/${item.field}` }] : [];
  });
  return <>
    {feed.error && <p role="status">Source unreachable. Showing saved items with their observation times.</p>}
    {entries.length ? <ul className={feed.error ? 'dash-world-stale' : undefined}>
      {entries.map((entry) => <li key={entry.key}>
        <strong>{entry.headline}</strong> · {entry.attribution} · <span>As of {displayTime(entry.asOf)}</span>
      </li>)}
    </ul> : <p>No attributed items are available from this source.</p>}
  </>;
}

export function WorldSources() {
  const { token } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const sources = usePoll(() => read<Bridge[]>(sdk, '/v1/bridges'), 30_000);
  const [selected, setSelected] = useState<string>();
  const source = sources.data?.find((bridge) => bridge.id === selected);
  return <>
    <PageHeader title="World" />
    <Card title="Sources">
      {denied(sources.error) ? <p>This account cannot view World sources.</p>
        : !sources.data ? <p role="status">{sources.error ? 'Could not load World sources.' : 'Checking sources…'}</p>
        : !sources.data.length ? <p>No bridges are registered on this hub.</p>
        : <>
          {sources.error && <p role="status">Could not refresh the sources. Showing the last list.</p>}
          <ul>{sources.data.map((bridge) => <li key={bridge.id}>
            <Button variant="ghost" aria-pressed={bridge.id === selected} onClick={() => setSelected(bridge.id)}>
              {bridge.provider} ({bridge.id})
            </Button>{' '}
            {bridge.state} · Last event {bridge.last_event_at ? displayTime(bridge.last_event_at) : 'unknown'}
          </li>)}</ul>
        </>}
    </Card>
    {source && !denied(sources.error) && <Card title={source.provider}><SourceItems key={source.id} sdk={sdk} bridge={source} /></Card>}
  </>;
}

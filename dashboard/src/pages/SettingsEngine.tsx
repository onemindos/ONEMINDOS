// SPDX-License-Identifier: Apache-2.0
// Settings > About > Engine (issue #619): the message bus every machine talks over, from GET /v1/engine.
// Simple view shows three plain facts: is the bus running, how many machines are connected, how full
// its message store is. The owner also gets each machine's link and how far behind it is, and the
// per-account connections under "Technical details". Everything is the hub's own reading of its
// NATS server; nothing is made up, and a number nobody reported is a dash. Refreshes every 5 s.
import { useMemo } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Card, Meter, StatusPill, Table, type Column } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

type Engine = components['schemas']['EngineView'];
type EngineNode = components['schemas']['EngineNode'];
type EngineAccount = components['schemas']['EngineAccount'];

export const ENGINE_REFRESH_MS = 5_000;

const mib = (b: number | null | undefined) => (typeof b === 'number' ? `${(b / 1048576).toFixed(1)} MiB` : '–');
const num = (n: number | null | undefined) => (typeof n === 'number' ? String(n) : '–');

function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}

const NODE_COLUMNS: Column<EngineNode>[] = [
  { key: 'node', header: 'Machine', render: (n) => <code>{n.node_id}</code>, sortValue: (n) => n.node_id },
  {
    key: 'link',
    header: 'Link',
    render: (n) => <StatusPill tone={n.link === 'up' ? 'ok' : n.link === 'down' ? 'warn' : 'neutral'} label={n.link === 'up' ? 'Connected' : n.link === 'down' ? 'Not connected' : 'Unknown'} />,
    sortValue: (n) => n.link,
  },
  { key: 'lag', header: 'Messages behind', align: 'end', render: (n) => num(n.outbox?.lag), sortValue: (n) => n.outbox?.lag ?? -1 },
  { key: 'rtt', header: 'Round trip', align: 'end', render: (n) => n.rtt ?? '–' },
];

const ACCOUNT_COLUMNS: Column<EngineAccount>[] = [
  { key: 'account', header: 'Account', render: (a) => <code>{a.account}</code>, sortValue: (a) => a.account },
  { key: 'conns', header: 'Connections', align: 'end', render: (a) => String(a.connections), sortValue: (a) => a.connections },
  { key: 'leafs', header: 'Leaf links', align: 'end', render: (a) => String(a.leafnodes), sortValue: (a) => a.leafnodes },
];

export function SettingsEngine() {
  const { token, mock } = useSignedIn();
  if (mock) {
    return (
      <Card title="Engine">
        <p role="status">Connect to a real hub to see its message bus. Demo mode has no engine data.</p>
      </Card>
    );
  }
  return <LiveEngine token={token} />;
}

function LiveEngine({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const res = usePoll(async () => {
    try {
      return await client.call<Engine>({ method: 'GET', path: '/v1/engine' });
    } catch (e) {
      throw apiError(e);
    }
  }, ENGINE_REFRESH_MS);
  // A child's role has no monitoring:read: the panel is simply not there for them.
  if (res.error?.status === 403) return null;
  const e = res.data;
  return (
    <Card title="Engine" subtitle="The message bus your machines talk over. It refreshes every few seconds.">
      {!e ? (
        <p className="om-hint" role="status">{res.error ? 'Could not read the engine: the hub did not answer.' : 'Loading…'}</p>
      ) : (
        <EngineBody e={e} behind={!!res.error} />
      )}
    </Card>
  );
}

function EngineBody({ e, behind }: { e: Engine; behind: boolean }) {
  const js = e.jetstream;
  const nodes = e.nodes ?? [];
  const accounts = e.accounts ?? [];
  const running = e.monitor.state === 'up' && e.health.status === 'ok';
  return (
    <div className="dash-stack">
      {behind && <p className="om-note om-tone-warn" role="status">Could not refresh: showing the last reading, not live.</p>}
      <p>
        <StatusPill tone={running ? 'ok' : 'warn'} label={running ? 'Running' : e.monitor.state === 'up' ? 'Not healthy' : 'Not answering'} />{' '}
        {e.links.up + e.links.down === 0
          ? 'No other machine is joined yet.'
          : `${e.links.up} ${e.links.up === 1 ? 'machine' : 'machines'} connected${e.links.down ? `, ${e.links.down} not connected` : ''}.`}
      </p>
      {e.health.status === 'unavailable' && e.health.error && <p className="om-hint">The bus says: {e.health.error}</p>}
      {js.state === 'refused' ? (
        <p className="om-note om-tone-warn" role="status">
          The message store is switched off because it has no size limit. {js.reason}
        </p>
      ) : js.enabled && typeof js.used_bytes === 'number' && typeof js.cap_bytes === 'number' && js.cap_bytes > 0 ? (
        <Meter label="Message store" value={js.used_bytes} max={js.cap_bytes} valueText={`${mib(js.used_bytes)} of ${mib(js.cap_bytes)} used`} />
      ) : (
        <p className="om-hint">Message store: {js.enabled === false ? 'off' : 'no reading'}.</p>
      )}
      {e.scope !== 'summary' && nodes.length > 0 && (
        <Table caption="Machines and their link to the hub" columns={NODE_COLUMNS} rows={nodes} rowKey={(n) => n.node_id} initialSort={{ key: 'node', dir: 'asc' }} empty={<p>No machine is joined.</p>} />
      )}
      {e.scope === 'all' && (
        <details className="dash-tech">
          <summary>Technical details</summary>
          <Table caption="Connections per NATS account" columns={ACCOUNT_COLUMNS} rows={accounts} rowKey={(a) => a.account} empty={<p>No connections.</p>} />
          <dl className="om-facts">
            <div>
              <dt>Slow consumers</dt>
              <dd>{num(e.slow_consumers?.total)}</dd>
            </div>
            <div>
              <dt>NATS version</dt>
              <dd>{e.server?.version ?? '–'}</dd>
            </div>
            <div>
              <dt>Streams</dt>
              <dd>{num(js.streams)}</dd>
            </div>
          </dl>
          <p className="om-hint">
            Read from <code>GET /v1/engine</code>, the hub&apos;s NATS monitor. On the box: <code>onemind nats status</code>.
          </p>
        </details>
      )}
    </div>
  );
}

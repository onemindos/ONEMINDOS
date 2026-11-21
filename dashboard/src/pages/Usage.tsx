// SPDX-License-Identifier: Apache-2.0
// Live usage (UMB-P11, #429): CPU, memory, disk and temperature per machine, and which app uses
// how much, from GET /v1/usage (the heartbeats and the app runtime; nothing is made up here).
// Refreshes every 5 s while the window is open. Old data is shown as old: a machine whose last
// heartbeat is over 30 s old, an app reading the runtime stopped answering, or a hub that did not
// answer the last refresh each say so, and their bars are dimmed. A number nobody reported is a
// dash, never 0.
import { useMemo } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Card, EmptyState, FreshnessPill, Meter, PageHeader, Table, type Column } from '@onemind/ui';
import { ApiError } from '../api/types';
import { formatAgo, secondsSince } from '../lib/time';
import { usePoll, useNow } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load } from './parts';

type Usage = components['schemas']['Usage'];
type UsageNode = components['schemas']['UsageNode'];
type UsageApp = components['schemas']['UsageApp'];

export const USAGE_REFRESH_MS = 5_000;

const gb = (mb: number) => `${(mb / 1024).toFixed(1)} GB`;
const dash = (v: number | null | undefined, f: (n: number) => string) => (typeof v === 'number' ? f(v) : '–');
const cores = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(2)} cores` : `${Math.round(m)} m`);
const mem = (m: number) => (m >= 1024 ? `${(m / 1024).toFixed(1)} GiB` : `${Math.round(m)} MiB`);
const FRESH = { online: 'live', stale: 'stale', offline: 'offline' } as const;

function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}

export function Usage() {
  const { token, person, mock } = useSignedIn();
  return mock ? (
    <>
      <PageHeader title="Live usage" />
      <p role="status">Connect to a real hub to see live usage. Demo mode has no usage data.</p>
    </>
  ) : (
    <LiveUsage key={person} token={token} />
  );
}

function MachineCard({ n }: { n: UsageNode }) {
  const notLive = n.stale;
  return (
    <Card
      as="article"
      level={3}
      variant={notLive ? 'stale' : 'default'}
      title={n.hostname ?? n.node_id}
      aside={<FreshnessPill state={FRESH[n.status as keyof typeof FRESH] ?? 'stale'} detail={notLive ? `last heard ${formatAgo(n.age_s)}` : undefined} />}
    >
      {notLive && <p className="om-note om-tone-warn">The numbers below are this machine’s last report from {formatAgo(n.age_s)}, not live.</p>}
      <div className="om-node-meters">
        {typeof n.cpu_pct === 'number' ? (
          <Meter label="Processor" value={n.cpu_pct} max={100} valueText={`${n.cpu_pct.toFixed(0)}% busy`} stale={notLive} />
        ) : (
          <p className="om-hint">Processor: this machine does not report it.</p>
        )}
        {typeof n.mem_used_mb === 'number' && typeof n.mem_total_mb === 'number' ? (
          <Meter label="Memory" value={n.mem_used_mb} max={n.mem_total_mb} valueText={`${gb(n.mem_used_mb)} of ${gb(n.mem_total_mb)} used`} stale={notLive} />
        ) : (
          <p className="om-hint">Memory: not reported.</p>
        )}
        {typeof n.disk_used_gb === 'number' && typeof n.disk_total_gb === 'number' ? (
          <Meter label="Disk" value={n.disk_used_gb} max={n.disk_total_gb} valueText={`${n.disk_used_gb.toFixed(1)} of ${n.disk_total_gb.toFixed(1)} GB used`} stale={notLive} />
        ) : (
          <p className="om-hint">Disk: not reported.</p>
        )}
      </div>
      <p className="om-hint">Temperature: {dash(n.temp_c, (t) => `${t.toFixed(0)} °C`)}{typeof n.temp_c !== 'number' ? ' (the hardware does not report it)' : ''}</p>
    </Card>
  );
}

const COLUMNS: Column<UsageApp>[] = [
  { key: 'name', header: 'App', render: (a) => a.name ?? a.app_id, sortValue: (a) => (a.name ?? a.app_id).toLowerCase() },
  { key: 'cpu', header: 'Processor', align: 'end', render: (a) => dash(a.cpu_millicores, cores), sortValue: (a) => a.cpu_millicores ?? -1 },
  { key: 'mem', header: 'Memory', align: 'end', render: (a) => dash(a.mem_mib, mem), sortValue: (a) => a.mem_mib ?? -1 },
  { key: 'disk', header: 'Disk', align: 'end', render: (a) => dash(a.disk_mib, mem), sortValue: (a) => a.disk_mib ?? -1 },
];

function LiveUsage({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const res = usePoll(async () => {
    try {
      return await client.call<Usage>({ method: 'GET', path: '/v1/usage' });
    } catch (e) {
      throw apiError(e);
    }
  }, USAGE_REFRESH_MS);
  const now = useNow(1000);
  return (
    <div className="dash-stack">
      <PageHeader title="Live usage" lede="Processor, memory and disk for each machine, and which apps use the most. It refreshes every few seconds while this window is open." />
      <Load res={res} what="Loading live usage">
        {(u) => {
          const behind = res.error ? secondsSince(new Date(res.fetchedAt ?? now).toISOString(), now) : null;
          const apps = u.apps;
          const sampled = apps.sampled_at ? secondsSince(apps.sampled_at, now) : null;
          return (
            <>
              {res.error && (
                <p className="om-note om-tone-warn" role="status">
                  Could not refresh: the hub did not answer. Showing the reading from {formatAgo(behind)}, not live.
                </p>
              )}
              {u.nodes.length === 0 ? (
                <EmptyState icon="nodes" title="No machines have reported yet">
                  <p>The hub lists a machine after its first heartbeat.</p>
                </EmptyState>
              ) : (
                <ul className="dash-grid" aria-label="Machines">
                  {u.nodes.map((n) => (
                    <li key={n.node_id}>
                      <MachineCard n={n} />
                    </li>
                  ))}
                </ul>
              )}
              <Card title="Apps" subtitle="Top users first. Disk is the data each app keeps on this box.">
                {apps.source === 'unavailable' ? (
                  <p className="om-note om-tone-warn" role="status">
                    This box has no app runtime the hub can read, so there are no per-app numbers. Nothing is guessed.
                  </p>
                ) : (
                  <>
                    {apps.stale && (
                      <p className="om-note om-tone-warn" role="status">
                        The app runtime has not answered since {formatAgo(sampled)}. These are the last numbers it gave, not live.
                      </p>
                    )}
                    <Table
                      caption="CPU, memory and disk per installed app"
                      hideCaption
                      columns={COLUMNS}
                      rows={apps.items}
                      rowKey={(a) => a.app_id}
                      initialSort={{ key: 'cpu', dir: 'desc' }}
                      empty={<p>No app is installed.</p>}
                    />
                  </>
                )}
              </Card>
            </>
          );
        }}
      </Load>
    </div>
  );
}

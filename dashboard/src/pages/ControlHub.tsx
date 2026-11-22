// SPDX-License-Identifier: Apache-2.0
// Control Hub (report ch. 3, as in Olares): the cluster-level view of the box for owners and
// adults. Machines with their k3s role and readiness (GET /v1/nodes), every workload with its state
// (GET /v1/apps), and the monitoring summary (GET /v1/monitoring/summary). Start, stop and restart
// file a request through the shared review dialog: nothing changes until an owner approves it.
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Button, Card, PageHeader, StatusPill, Table, formatAgo, secondsSince, type Column, type Tone } from '@onemind/ui';
import type { ActionType, CatalogApp, NodeRecord, NodeStatus } from '../api/types';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { useSignedIn } from '../session';
import { Load } from './parts';
import { LogsPanel } from './ControlHubLogs';
import { SecretsPanel } from './ControlHubSecrets';

const NODE_TONE: Record<NodeStatus, Tone> = { online: 'ok', stale: 'warn', offline: 'bad' };
// core/onemind_core/models.py CatalogApp.status: 'installed' is the running state.
const RUNNING = new Set(['installed']);
const MOVING = new Set(['starting', 'stopping', 'restarting', 'updating', 'configuring', 'removing', 'deleting_data', 'installing']);

export function appTone(status: string): Tone {
  if (RUNNING.has(status)) return 'ok';
  if (MOVING.has(status)) return 'info';
  if (status === 'failed') return 'bad';
  return 'neutral';
}

/** The workloads on the box: the same set the Installed screen lists. */
const ON_BOX = new Set(['stopped', 'failed', 'unknown', 'starting', 'stopping', 'restarting', 'updating', 'configuring', 'removing']);
export function workloads(apps: CatalogApp[]): CatalogApp[] {
  return apps.filter((a) => a.installed || ON_BOX.has(a.status));
}

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'secrets', label: 'Secrets' },
  { id: 'logs', label: 'Logs' },
] as const;
type TabId = (typeof TABS)[number]['id'];

/** The page: tabs over the cluster view. Metrics, Database and Login arrive in later slices. */
export function ControlHub() {
  const [params, setParams] = useSearchParams();
  const asked = params.get('tab');
  const tab: TabId = TABS.some((t) => t.id === asked) ? (asked as TabId) : 'overview';
  return (
    <div className="dash-stack">
      <PageHeader title="Control Hub" lede="Every machine and workload on this box. Each change files a request; nothing changes until an owner approves it." />
      <div role="tablist" aria-label="Control Hub" className="dash-actions">
        {TABS.map((t) => (
          <Button key={t.id} role="tab" id={`ch-tab-${t.id}`} aria-selected={tab === t.id} aria-controls="ch-panel" size="sm" variant={tab === t.id ? 'primary' : 'ghost'} onClick={() => setParams(t.id === 'overview' ? {} : { tab: t.id }, { replace: true })}>{t.label}</Button>
        ))}
      </div>
      <div role="tabpanel" id="ch-panel" aria-labelledby={`ch-tab-${tab}`} className="dash-stack">
        {tab === 'overview' ? <Overview /> : <AppTab kind={tab} />}
      </div>
    </div>
  );
}

/** Secrets and Logs act on one app: pick it, and the panel below is keyed on it so state never leaks across apps. */
function AppTab({ kind }: { kind: 'secrets' | 'logs' }) {
  const hub = useHub();
  const apps = workloads(hub.apps.data ?? []).filter((a) => a.installed);
  const [picked, setPicked] = useState<string>();
  const app = apps.find((a) => a.id === picked) ?? apps[0];
  if (!hub.apps.data) return <Load res={hub.apps} what="Loading workloads">{() => null}</Load>;
  if (!app) return <p className="om-hint">Nothing is installed yet.</p>;
  const name = app.name ?? app.id;
  return (
    <>
      <label>
        App{' '}
        <select value={app.id} onChange={(e) => setPicked(e.target.value)}>
          {apps.map((a) => <option key={a.id} value={a.id}>{a.name ?? a.id}</option>)}
        </select>
      </label>
      {kind === 'secrets' ? <SecretsPanel key={app.id} app={{ id: app.id, name }} /> : <LogsPanel key={app.id} appId={app.id} />}
    </>
  );
}

function Overview() {
  const hub = useHub();
  const { api } = useSignedIn();
  const { requestApp } = useShell();
  const summary = usePoll(() => api.monitoring(), 30_000);
  const nodes = hub.nodes.data ?? [];
  const apps = workloads(hub.apps.data ?? []);
  const waiting = hub.actionList.filter((a) => a.state === 'awaiting_approval').length;
  const canAsk = hub.canRequest !== 'no';

  const ask = (type: ActionType, a: CatalogApp) => void requestApp(type, a.id);

  const nodeCols: Column<NodeRecord>[] = [
    { key: 'host', header: 'Machine', render: (n) => n.hostname, sortValue: (n) => n.hostname },
    { key: 'status', header: 'State', render: (n) => { const s = hub.nodeStatus(n); return <StatusPill tone={NODE_TONE[s]} label={s} detail={`last seen ${formatAgo(secondsSince(n.last_seen, hub.now))}`} />; } },
    { key: 'k3s', header: 'Cluster', render: (n) => (n.k3s.present ? `${n.k3s.role ?? 'member'}, ${n.k3s.ready ? 'ready' : 'not ready'}` : 'not in the cluster') },
    { key: 'slot', header: 'A/B slot', render: (n) => (n.rauc.present ? n.rauc.booted_slot ?? 'unknown' : 'no A/B'), secondary: true },
    { key: 'mem', header: 'Memory free', render: (n) => `${n.mem_available_mb} of ${n.mem_total_mb} MB`, secondary: true },
  ];
  const appCols: Column<CatalogApp>[] = [
    { key: 'name', header: 'Workload', render: (a) => <Link to={href.manage(a.id)}>{a.name ?? a.id}</Link>, sortValue: (a) => a.name ?? a.id },
    { key: 'status', header: 'State', render: (a) => <StatusPill tone={appTone(a.status)} label={a.status === 'installed' ? 'running' : a.status} /> },
    { key: 'version', header: 'Version', render: (a) => a.version ?? 'unknown', secondary: true },
    {
      key: 'do',
      header: 'Request',
      render: (a) =>
        canAsk ? (
          <div className="dash-actions">
            {RUNNING.has(a.status) ? (
              <>
                <Button size="sm" variant="secondary" aria-label={`Request restart of ${a.name ?? a.id}`} onClick={() => ask('app.restart', a)}>Restart</Button>
                <Button size="sm" variant="ghost" aria-label={`Request stop of ${a.name ?? a.id}`} onClick={() => ask('app.stop', a)}>Stop</Button>
              </>
            ) : (
              <Button size="sm" variant="secondary" aria-label={`Request start of ${a.name ?? a.id}`} onClick={() => ask('app.start', a)}>Start</Button>
            )}
          </div>
        ) : (
          <span className="om-hint">owner only</span>
        ),
    },
  ];

  return (
    <>
      <Load res={summary} what="Loading the summary">
        {(s) => (
          <Card title="Right now" variant="sunken">
            <dl className="om-facts">
              <div><dt>Machines online</dt><dd>{s.nodes.online} of {s.nodes.online + s.nodes.stale + s.nodes.offline}</dd></div>
              <div><dt>Workloads</dt><dd>{Object.entries(s.apps).map(([k, v]) => `${v} ${k}`).join(', ') || 'none'}</dd></div>
              <div><dt>Open alerts</dt><dd>{s.open_alerts.critical} critical, {s.open_alerts.warning} warning, {s.open_alerts.info} info</dd></div>
              <div><dt>Waiting for approval</dt><dd><Link to={href.approvals}>{waiting}</Link></dd></div>
            </dl>
          </Card>
        )}
      </Load>
      <Load res={hub.nodes} what="Loading machines">
        {() => <Table caption="Machines" columns={nodeCols} rows={nodes} rowKey={(n) => n.node_id} empty="No machines have reported yet." />}
      </Load>
      <Load res={hub.apps} what="Loading workloads">
        {() => <Table caption="Workloads" columns={appCols} rows={apps} rowKey={(a) => a.id} empty="Nothing is installed yet." />}
      </Load>
    </>
  );
}

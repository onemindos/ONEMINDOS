// SPDX-License-Identifier: Apache-2.0
// FD-06: one page per app. A state dot that combines health, restarts, the last scan and a waiting
// update (anything unread makes it grey, never green), a facts card, and the tabs Usage, Logs,
// Alerts, Backups, Access, Trust, Help, plus Workloads for owners and adults.
// Read-only on purpose: every change (restart, update, remove, sharing) stays an approval request,
// made from Installed > manage (#139/#490 own the Open button and its sign-in) or from Approvals.
// Box-wide live usage is #441; this page shows the one app's own numbers from /v1/apps/{id}/metrics.
import { useMemo } from 'react';
import { Link, useParams } from 'react-router';
import { OneMind } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, Tabs, safeHttpUrl, type TabDef, type Tone } from '@onemind/ui';
import type { CatalogApp } from '../api/types';
import { useHub } from '../data/hub';
import { appState, type AppDot, type AppHealth, type Fact } from '../lib/appState';
import { appPageHref, readAppView, readSharing, readSnapshots, readUsage, type AppView } from '../lib/appPage';
import { usePoll } from '../lib/hooks';
import { needs } from '../lib/needs';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { Load } from './parts';
import { AppMachineFit } from './AppMachineFit';

const TONE: Record<AppDot, Tone> = { ok: 'ok', warn: 'warn', bad: 'bad', neutral: 'neutral', unknown: 'neutral' };
const day = (iso: string | null | undefined) => (iso && !Number.isNaN(Date.parse(iso)) ? iso.slice(0, 10) : 'Not reported');
const cpu = (v: number | null) => (v === null ? 'Not reported' : `${v} millicores`);
const mem = (v: number | null) => (v === null ? 'Not reported' : `${v} MB`);

export function AppPage() {
  const { appId = '' } = useParams();
  const hub = useHub();
  const { mock } = useSignedIn();
  const app = hub.apps.data?.find((a) => a.id === appId);
  if (!app) return <p role="status">{hub.apps.error?.message ?? (hub.apps.loading ? 'Loading app…' : 'App not found.')}</p>;
  return mock ? <Page key={appId} app={app} /> : <LivePage key={appId} app={app} />;
}

function LivePage({ app }: { app: CatalogApp }) {
  const { token } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  return <Page app={app} sdk={sdk} />;
}

function Page({ app, sdk }: { app: CatalogApp; sdk?: OneMind }) {
  const hub = useHub();
  const shell = useShell();
  const view = usePoll(async () => {
    if (!sdk) throw new Error('Connect to a real hub to read this app’s health. Demo mode has none.');
    return readAppView(sdk, app.id);
  }, 30_000);
  const name = app.name || app.id;
  const source = safeHttpUrl(app.source); // the licence's source duty (AGPL apps such as Vaultwarden): a real link
  const health: Fact<AppHealth> = view.data ? { state: 'ok', value: { ...view.data.health, restarts: view.data.restarts } } : view.error ? { state: 'failed' } : { state: 'absent' };
  const loadingHealth = !view.data && !view.error;
  const st = appState({
    status: { state: 'ok', value: app.status },
    health,
    scan: { state: 'ok', value: app.scan },
    update: { state: 'absent' },
  }, hub.now);
  const dot = loadingHealth ? undefined : st;
  const pro = shell.view === 'pro';
  const tabs: TabDef[] = [
    { id: 'usage', label: 'Usage', content: <UsageTab appId={app.id} sdk={sdk} /> },
    { id: 'logs', label: 'Logs', content: <LogsTab appId={app.id} /> },
    { id: 'alerts', label: 'Alerts', content: <AlertsTab appId={app.id} /> },
    { id: 'backups', label: 'Backups', content: <BackupsTab appId={app.id} sdk={sdk} pro={pro} /> },
    { id: 'access', label: 'Access', content: <AccessTab appId={app.id} sdk={sdk} view={view.data} /> },
    { id: 'trust', label: 'Trust', content: <TrustTab app={app} now={hub.now} /> },
    { id: 'help', label: 'Help', content: <HelpTab app={app} dot={st.dot} /> },
    ...(pro ? [{ id: 'workloads', label: 'Workloads', content: <WorkloadsTab appId={app.id} sdk={sdk} view={view.data} /> }] : []),
  ];
  return <div className="dash-stack">
    <PageHeader title={name} lede={app.description ?? undefined} />
    <Card title="State" variant={dot && (dot.dot === 'bad') ? 'attention' : 'default'} aside={dot ? <StatusPill tone={TONE[dot.dot]} label={dot.label} /> : <StatusPill tone="neutral" label="Checking" />}>
      {loadingHealth ? <p role="status">Reading health…</p> : <>
        {dot!.reasons.length ? <ul aria-label="Why">{dot!.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : <p>Running, scanned and not restarting.</p>}
        {view.error && <p><Button onClick={() => void view.reload()}>Try again</Button></p>}
      </>}
      <dl className="om-facts">
        <div><dt>Status</dt><dd>{app.status}</dd></div>
        <div><dt>Version</dt><dd>{app.version ?? 'Not reported'}</dd></div>
        <div><dt>Licence</dt><dd>{app.license ?? 'Not reported'}</dd></div>
        <div><dt>Source</dt><dd>{source ? <a href={source} target="_blank" rel="noopener noreferrer">{app.source}</a> : (app.source ?? 'Not reported')}</dd></div>
        <div><dt>Category</dt><dd>{app.category ?? 'Not reported'}</dd></div>
      </dl>
      <p className="om-hint">Every change is a request an owner approves. <a href={href.manage(app.id)}>Open and manage {name}</a> · <a href={href.app(app.id)}>Market page</a></p>
    </Card>
    <Tabs label={`${name} details`} tabs={tabs} />
    {pro && <AppMachineFit key={app.id} appId={app.id} />}
  </div>;
}

function Gone({ what }: { what: string }) {
  return <p role="status">{what} comes from a real hub. Demo mode has none.</p>;
}

function UsageTab({ appId, sdk }: { appId: string; sdk?: OneMind }) {
  const usage = usePoll(async () => { if (!sdk) throw new Error('no hub'); return readUsage(sdk, appId); }, 15_000);
  if (!sdk) return <Gone what="Usage" />;
  return <Load res={usage} what="Loading usage">{(u) => {
    const sum = (k: 'cpuMillicores' | 'memMb') => (u.components.length === 0 || u.components.some((c) => c[k] === null) ? null : Math.round(u.components.reduce((n, c) => n + (c[k] ?? 0), 0) * 10) / 10);
    return <>
      <dl className="om-facts">
        <div><dt>CPU</dt><dd>{cpu(sum('cpuMillicores'))}</dd></div>
        <div><dt>Memory</dt><dd>{mem(sum('memMb'))}</dd></div>
        <div><dt>Sampled</dt><dd>{u.at ?? 'Not reported'}</dd></div>
      </dl>
      {u.components.length === 0 && <p>The hub reports no running parts for this app, so there is nothing to measure.</p>}
    </>;
  }}</Load>;
}

function LogsTab({ appId }: { appId: string }) {
  const { api } = useSignedIn();
  const logs = usePoll(async () => {
    if (!api.appLogs) throw new Error('Logs cannot be read by this gateway client.');
    return api.appLogs(appId);
  }, 0);
  return <Load res={logs} what="Loading logs">{(text) => <>
    <pre aria-label="Last log lines">{text || 'The gateway returned no log lines.'}</pre>
    <Button onClick={() => void logs.reload()}>Refresh logs</Button>
  </>}</Load>;
}

function AlertsTab({ appId }: { appId: string }) {
  const { api } = useSignedIn();
  const link = appPageHref(appId);
  const alerts = usePoll(async () => (await api.alerts('open')).filter((a) => a.subject?.app_id === appId), 30_000);
  const notes = usePoll(async () => (await api.notifications({ limit: 100 })).filter((n) => n.link === link), 30_000);
  return <>
    <h3>Open alerts</h3>
    <Load res={alerts} what="Loading alerts">{(list) => list.length === 0 ? <p>No open alert for this app.</p> : <ul>{list.map((a) => <li key={a.id}><strong>{a.title}</strong> ({a.severity}){a.body ? ` — ${a.body}` : ''}</li>)}</ul>}</Load>
    <h3>Notifications</h3>
    <Load res={notes} what="Loading notifications">{(list) => list.length === 0 ? <p>No notification about this app.</p> : <ul>{list.map((n) => <li key={n.id}><strong>{n.title}</strong>{n.read_at ? '' : ' (unread)'} — {n.body} <small>{day(n.created_at)}</small></li>)}</ul>}</Load>
    <p className="om-hint"><a href={href.alerts}>All alerts</a>. Asking for a fix there files a request that waits in Approvals.</p>
  </>;
}

function BackupsTab({ appId, sdk, pro }: { appId: string; sdk?: OneMind; pro: boolean }) {
  const snaps = usePoll(async () => { if (!sdk) throw new Error('no hub'); return readSnapshots(sdk, appId); }, 60_000);
  if (!sdk) return <Gone what="Backup history" />;
  return <>
    <Load res={snaps} what="Loading restore points">{(list) => list.length === 0 ? <p>No restore point for this app yet.</p> : <table>
      <caption>Restore points for this app, newest first</caption>
      <thead><tr><th scope="col">Taken</th><th scope="col">Why</th><th scope="col">Checked</th></tr></thead>
      <tbody>{list.map((s) => <tr key={s.id}><td>{day(s.takenAt)}</td><td>{s.reason ?? 'Not reported'}</td><td>{s.verifiedAt ? day(s.verifiedAt) : 'Not checked yet'}</td></tr>)}</tbody>
    </table>}</Load>
    <p className="om-hint">Restoring is a request an owner approves.{pro && <> <a href={href.backups}>Open Backups</a>.</>}</p>
  </>;
}

function AccessTab({ appId, sdk, view }: { appId: string; sdk?: OneMind; view?: AppView }) {
  const access = usePoll(async () => { if (!sdk) throw new Error('no hub'); return readSharing(sdk, appId); }, 0);
  if (!sdk) return <Gone what="Sharing" />;
  return <Load res={access} what="Loading sharing">{(a) => {
    const mine = a.allowed ?? view?.access?.sharedWithMe ?? null;
    return <>
    <dl className="om-facts">
      <div><dt>Roles that can open it</dt><dd>{a.roles.length ? a.roles.join(', ') : 'None'}</dd></div>
      <div><dt>People added by name</dt><dd>{a.people.length ? a.people.map((p) => p.name).join(', ') : 'None'}</dd></div>
      <div><dt>Sign-in</dt><dd>{a.auth === 'app' ? 'The app’s own sign-in' : a.auth === 'onemind' ? 'OneMind sign-in' : 'Not reported'}</dd></div>
      {mine !== null && <div><dt>You</dt><dd>{mine ? 'You can open it' : 'You cannot open it'}</dd></div>}
    </dl>
    <p className="om-hint">Only an owner changes sharing, under <Link to="/settings/permissions">Settings &gt; Permissions &gt; By app</Link>; adding people asks for a passkey.</p>
    </>;
  }}</Load>;
}

function TrustTab({ app, now }: { app: CatalogApp; now: number }) {
  const scan = app.scan;
  const links = (['docs', 'github', 'website', 'support'] as const).filter((k) => safeHttpUrl(app.links?.[k]));
  const tier = app.tier === 'verified' ? 'Verified' : app.tier === 'community' ? 'Community' : app.tier === 'blocked' ? 'Blocked' : 'Not reported';
  const ageDays = scan ? Math.floor((now - Date.parse(scan.scanned_at)) / 86_400_000) : null;
  return <dl className="om-facts">
    <div><dt>Market tier</dt><dd>{tier}</dd></div>
    <div><dt>Last security scan</dt><dd>{scan ? `${scan.result === 'pass' ? 'Passed' : 'Failed'} on ${day(scan.scanned_at)}${ageDays !== null && ageDays > 7 ? ' (older than 7 days)' : ''}` : 'Never scanned'}</dd></div>
    <div><dt>Licence</dt><dd>{app.license ?? 'Not reported'}</dd></div>
    <div><dt>Version</dt><dd>{app.version ?? 'Not reported'}</dd></div>
    <div><dt>Runs on</dt><dd>{app.archs.length ? app.archs.join(', ') : 'Not reported'}</dd></div>
    <div><dt>Needs</dt><dd>{needs(app)}</dd></div>
    {links.length > 0 && <div><dt>Project</dt><dd>{links.length} link{links.length === 1 ? '' : 's'} under Help</dd></div>}
  </dl>;
}

const NEXT: Record<AppDot, string> = {
  ok: 'Nothing to do.',
  warn: 'Open the Logs and Alerts tabs to see why, then ask for a restart from the manage page if it keeps happening.',
  bad: 'Read the Logs tab, then ask for a restart from the manage page. An owner approves it.',
  neutral: 'It is stopped. Ask for a start from the manage page.',
  unknown: 'The hub could not tell. Try again in a minute; if it stays unknown, check the box under Machines.',
};

function HelpTab({ app, dot }: { app: CatalogApp; dot: AppDot }) {
  const links = (['docs', 'support', 'website', 'github'] as const).map((k) => [k, safeHttpUrl(app.links?.[k])] as const).filter((x): x is readonly [typeof x[0], string] => !!x[1]);
  const label = { docs: 'Documentation', support: 'Get support', website: 'Website', github: 'Source code' } as const;
  return <>
    <p>{NEXT[dot]}</p>
    <ul aria-label="Project links">{links.length ? links.map(([k, url]) => <li key={k}><a href={url} target="_blank" rel="noopener noreferrer">{label[k]}</a></li>) : <li>The app lists no project links.</li>}</ul>
    <p><a href={href.manage(app.id)}>Manage this app</a> · <a href={href.activity}>Activity</a></p>
  </>;
}

function WorkloadsTab({ appId, sdk, view }: { appId: string; sdk?: OneMind; view?: AppView }) {
  const usage = usePoll(async () => { if (!sdk) throw new Error('no hub'); return readUsage(sdk, appId); }, 15_000);
  if (!sdk) return <Gone what="Workloads" />;
  const comps = view?.components ?? [];
  const byName = new Map((usage.data?.components ?? []).map((c) => [c.name, c]));
  if (comps.length === 0) return <p>{view ? 'The hub reports no running parts for this app.' : 'The parts are not known yet: health could not be read.'}</p>;
  return <>
    <table>
      <caption>The parts this app runs (read only)</caption>
      <thead><tr><th scope="col">Part</th><th scope="col">Ready</th><th scope="col">Restarts</th><th scope="col">Last stop</th><th scope="col">CPU</th><th scope="col">Memory</th></tr></thead>
      <tbody>{comps.map((c) => <tr key={c.name}><th scope="row">{c.name}</th><td>{c.ready ? 'Yes' : 'No'}</td><td>{c.restarts}</td><td>{c.lastExit ?? 'None'}</td><td>{cpu(byName.get(c.name)?.cpuMillicores ?? null)}</td><td>{mem(byName.get(c.name)?.memMb ?? null)}</td></tr>)}</tbody>
    </table>
    {usage.error && <p role="status">CPU and memory could not be read right now.</p>}
  </>;
}

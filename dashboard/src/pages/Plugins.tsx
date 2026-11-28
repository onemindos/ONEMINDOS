// SPDX-License-Identifier: Apache-2.0
// Atlas Plugins (design screen 10, #654). Real data from GET /v1/plugins: each installed plugin, which of the five defined
// places it uses (Home tile, Map layer, Settings panel, Commands, Dock item) and whether a person must approve its commands.
// Restart, Disable, Enable and Update go through the same reviewed request path as every app change (preview, then a request
// that waits in Approvals, D-027); this page never changes anything itself. A plugin that stopped or failed is marked on its own
// row; nothing else on the page depends on it.
import { useState } from 'react';
import { Link } from 'react-router';
import { Button, Card, EmptyState, PageHeader, StatusPill, formatAgo } from '@onemind/ui';
import type { OneMindApi, PluginInfo } from '../api/client';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useHub } from '../data/hub';
import { useShell } from '../shell/Shell';
import { Load } from './parts';

type Slot = NonNullable<PluginInfo['slots']>[number];

/** The design's five places, in its order, with what each one means in plain words. */
export const PLACES: { slot: Slot['slot']; label: string; adds: string }[] = [
  { slot: 'home_tile', label: 'Home tile', adds: 'A tile on Home' },
  { slot: 'map_layer', label: 'Map layer', adds: 'Its own layer on the Map' },
  { slot: 'settings_panel', label: 'Settings panel', adds: 'Its own settings' },
  { slot: 'commands', label: 'Commands', adds: 'Commands you can run from the CLI and the run bar' },
  { slot: 'dock_item', label: 'Dock item', adds: 'Opens its own window from the dock' },
];

export function Plugins() {
  const { api } = useSignedIn();
  if (!api.plugins) return <EmptyState icon="apps" title="Connect to a gateway to see plugins" command="onemind plugins list" />;
  return <Connected api={api as OneMindApi & Required<Pick<OneMindApi, 'plugins'>>} />;
}

function Connected({ api }: { api: Required<Pick<OneMindApi, 'plugins'>> }) {
  const hub = useHub();
  const res = usePoll(() => api.plugins(), 10_000);
  void hub.now; // re-render on the hub clock so the age keeps counting
  const age = res.fetchedAt === undefined ? undefined : formatAgo(Math.max(0, Math.round((Date.now() - res.fetchedAt) / 1000)));
  return <div className="dash-stack dash-plugins">
    <PageHeader title="Plugins" lede="Plugins add things in defined places. Each one runs on its own, so one that misbehaves is marked Paused or Failed on its own row and nothing else changes." />
    {age && <p className="om-hint" role="status">Read from the gateway {age}.</p>}
    <Load res={res} what="Loading plugins">{(list) => list.length === 0
      ? <EmptyState icon="apps" title="No plugins installed" command="onemind plugins list">
        A plugin adds a tile, a Map layer, a settings panel, commands or a dock item. Install one from the Market or with <code>onemind app</code>, and it shows up here with the places it uses.
      </EmptyState>
      : <Master list={list} />}</Load>
  </div>;
}

function Master({ list }: { list: PluginInfo[] }) {
  const shell = useShell();
  const hub = useHub();
  const [pick, setPick] = useState<string>();
  const sel = list.find((p) => p.id === pick) ?? list[0]!;
  const stopped = list.filter((p) => p.status === 'stopped').length;
  const failedN = list.filter((p) => p.status === 'failed').length;
  const ask = (type: 'app.restart' | 'app.stop' | 'app.start' | 'app.update') => void shell.requestApp(type, sel.id);
  const paused = sel.status === 'stopped';
  const failed = sel.status === 'failed';
  const offered = hub.apps.data?.find((a) => a.id === sel.id)?.version ?? null;
  const canUpdate = !!offered && !!sel.installed_version && offered !== sel.installed_version;
  return <div className="dash-plugins-grid">
    <nav aria-label="Installed plugins" className="dash-plugins-list">
      <h2>Installed · {list.length}{stopped > 0 ? ` · ${stopped} paused` : ''}{failedN > 0 ? ` · ${failedN} failed` : ''}</h2>
      {list.map((p) => <button key={p.id} type="button" className="dash-plugins-item" aria-current={p.id === sel.id ? 'true' : undefined} onClick={() => setPick(p.id)}>
        <span><b>{p.name}</b><small>{p.installed_version ? `v${p.installed_version}` : 'version unknown'}</small></span>
        <State status={p.status} />
      </button>)}
    </nav>
    <section aria-label={`${sel.name} places`} className="dash-plugins-detail">
      <h2>{sel.name} <State status={sel.status} /></h2>
      <p>Here is every place this plugin can show up, and when a person has to say yes.</p>
      <table className="dash-plugins-table">
        <caption className="om-visually-hidden">Places used by {sel.name}</caption>
        <thead><tr><th scope="col">Place</th><th scope="col">What it adds</th><th scope="col">Declared</th><th scope="col">Who decides</th></tr></thead>
        <tbody>{PLACES.map((pl, i) => {
          const s = (sel.slots ?? []).find((x) => x.slot === pl.slot);
          return <tr key={pl.slot}>
            <th scope="row"><span className="dash-plugins-n" aria-hidden="true">{i + 1}</span> {pl.label}</th>
            <td>{s?.declared && s.names?.length ? s.names.join(', ') : pl.adds}</td>
            <td>{s?.declared ? 'Yes' : 'Not declared'}</td>
            <td>{s?.declared && s.approval === 'each_time' ? 'A person approves each call' : s?.declared ? 'Nothing to approve' : 'Not applicable'}</td>
          </tr>;
        })}</tbody>
      </table>
      <p className="om-hint">Version {sel.installed_version ?? 'unknown'}. An update is kept only if it comes up healthy; otherwise the previous revision returns by itself. Rolling back to an older version is not offered for plugins yet.</p>
    </section>
    <aside aria-label="When a plugin misbehaves" className="dash-plugins-side">
      <Card title="When a plugin misbehaves" variant="sunken">
        {failed
          ? <p><b>{sel.name} failed.</b> Its tile shows a notice. The rest of OneMind keeps working. Restart it, or disable it until you have looked.</p>
          : paused
          ? <p><b>{sel.name} is paused.</b> Its tile shows a notice. The rest of OneMind keeps working.</p>
          : <p>If {sel.name} stops responding, only its own tile pauses. Restart it, or disable it until you have looked.</p>}
        <div className="dash-plugins-actions">
          <Button disabled={paused} onClick={() => ask('app.restart')}>Restart</Button>
          {paused ? <Button variant="primary" onClick={() => ask('app.start')}>Enable</Button> : <Button variant="primary" onClick={() => ask('app.stop')}>Disable</Button>}
          <Button disabled={!canUpdate} onClick={() => ask('app.update')}>{canUpdate ? `Review update to ${offered}` : 'Up to date'}</Button>
        </div>
        <p className="om-hint">Each button files a request that waits for an owner in <Link to="/approvals">Approvals</Link>. Nothing runs until it is approved.</p>
        <code className="dash-plugins-cmd">$ onemind plugins {paused ? 'enable' : 'disable'} {sel.id}</code>
      </Card>
      <Card title="A plugin can never" variant="sunken">
        <ul className="dash-plugins-never">
          <li>run a command that changes something without a person's yes</li>
          <li>appear anywhere except the five places listed here</li>
        </ul>
      </Card>
    </aside>
  </div>;
}

function State({ status }: { status: PluginInfo['status'] }) {
  if (status === 'failed') return <StatusPill tone="bad" label="Failed" glyph="bad" />;
  if (status === 'stopped') return <StatusPill tone="warn" label="Paused" glyph="warn" />;
  return <StatusPill tone="ok" label="Running" glyph="ok" />;
}

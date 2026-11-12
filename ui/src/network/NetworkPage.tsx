// SPDX-License-Identifier: Apache-2.0
// Network page (CORE-NET-13; NETWORKING.md §12 "Network page"): how the box is reached, every
// machine on the private mesh with its link, the names in use, and the installed apps' addresses.
// No IP address is shown by default (contract §2); "Show addresses" is an owner-only toggle that
// is not remembered.
import { useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { StatusPill } from '../components/StatusPill';
import { Table, type Column } from '../components/Table';
import { formatAgo, secondsSince } from '../lib/time';
import type { Tone } from '../tokens/tokens';
import { PATH_LABEL, ROLE_LABEL, machineRows, pendingJoins, type MachineRow } from './logic';
import type { FabricSummary, Loadable, MeshView } from './types';
import './network.css';

export interface NetworkPageProps {
  mesh: Loadable<MeshView>;
  fabric: Loadable<FabricSummary>;
  now: number;
  /** Owners may reveal mesh addresses; the page asks the parent to re-read with ?addresses=1. */
  isOwner: boolean;
  onShowAddresses?: (show: boolean) => void;
  onAddDevice: () => void;
  /** Opens the approval card of a waiting join (Approvals, with the match code). */
  onReviewJoin?: (actionId: string) => void;
  onRetry: () => void;
}

const STATUS: Record<MachineRow['status'], { tone: Tone; label: string }> = {
  online: { tone: 'ok', label: 'Online' },
  joining: { tone: 'info', label: 'Joining' },
  stale: { tone: 'warn', label: 'Not heard from recently' },
  offline: { tone: 'bad', label: 'Offline' },
  down: { tone: 'bad', label: 'Mesh down' },
};

const MODE: Record<MeshView['mode'], { tone: Tone; label: string; help: string }> = {
  lan: { tone: 'ok', label: 'Home network', help: 'Machines on your home network reach each other over the encrypted mesh. Nothing is open to the internet.' },
  relay: { tone: 'info', label: 'Through your relay', help: 'Your phones and remote machines reach the box through your own relay server.' },
  direct: { tone: 'info', label: 'Direct', help: 'Your router forwards the mesh ports to the box.' },
  hosted: { tone: 'warn', label: 'Tailscale hosted', help: 'A third-party coordinator is in use.' },
  off: { tone: 'neutral', label: 'Mesh off', help: 'This box runs without the private mesh.' },
};

export function NetworkPage({ mesh, fabric, now, isOwner, onShowAddresses, onAddDevice, onReviewJoin, onRetry }: NetworkPageProps) {
  const [showIps, setShowIps] = useState(false); // never remembered (NETWORKING §12)

  if (mesh.state === 'loading' || fabric.state === 'loading') {
    return <div className="om-net" aria-busy="true"><Card title="Network"><p className="om-net-muted">Reading the network…</p></Card></div>;
  }
  if (mesh.state === 'error' || fabric.state === 'error') {
    const message = mesh.state === 'error' ? mesh.message : fabric.state === 'error' ? fabric.message : '';
    return (
      <div className="om-net">
        <Card title="Network" variant="attention" footer={<Button onClick={onRetry} icon="updates">Try again</Button>}>
          <p>The hub did not answer: {message}</p>
        </Card>
      </div>
    );
  }
  const m = mesh.data;
  const f = fabric.data;
  const stale = mesh.staleSince ?? fabric.staleSince;
  const rows = machineRows(m, f);
  const waiting = pendingJoins(f);
  const mode = MODE[m.mode];

  const columns: Column<MachineRow>[] = [
    { key: 'name', header: 'Machine', render: (r) => <span className="om-net-name">{r.name}</span>, sortValue: (r) => r.name },
    { key: 'role', header: 'Role', render: (r) => ROLE_LABEL[r.role] },
    { key: 'status', header: 'State', render: (r) => <StatusPill {...STATUS[r.status]} /> },
    { key: 'path', header: 'Link to the hub', render: (r) => (r.role === 'hub' ? '—' : PATH_LABEL[r.path]), secondary: true },
    {
      key: 'leaf', header: 'Event bus', secondary: true,
      render: (r) => (r.role === 'hub' ? '—' : r.leaf === 'up' ? 'Connected' : r.leaf === 'down' ? 'Disconnected' : 'Not reported'),
    },
    ...(showIps ? [{ key: 'ip', header: 'Mesh address', render: (r: MachineRow) => <code>{r.meshIp ?? '—'}</code> }] : []),
  ];

  return (
    <div className="om-net">
      <Card
        title="Reach"
        variant={stale ? 'stale' : 'default'}
        aside={<StatusPill tone={mode.tone} label={mode.label} detail={stale ? `last known ${formatAgo(secondsSince(stale, now))}` : undefined} />}
      >
        <p>{mode.help}</p>
        <dl className="om-net-facts">
          <div><dt>Coordinator</dt><dd><StatusPill tone={m.control.state === 'up' ? 'ok' : m.control.state === 'off' ? 'neutral' : 'bad'} label={m.control.state === 'up' ? 'Running' : m.control.state === 'off' ? 'Off' : 'Not answering'} /></dd></div>
          <div><dt>Connections</dt><dd>{m.https ? 'HTTPS with this box’s own certificate' : 'Plain HTTP (HTTPS is off)'}</dd></div>
          <div><dt>Box certificate</dt><dd><code className="om-net-fp" title={m.ca_sha256}>{m.ca_sha256.slice(0, 16)}…</code></dd></div>
        </dl>
      </Card>

      {waiting.length > 0 && (
        <Card title="Waiting for you" variant="attention" level={2}>
          <ul className="om-net-list">
            {waiting.map((j) => (
              <li key={j.join_request_id}>
                <span><strong>{j.hostname}</strong> wants to join as a {ROLE_LABEL[j.role].toLowerCase()}. Its code: <code className="om-net-code">{j.match_code}</code></span>
                {onReviewJoin && <Button size="sm" variant="primary" onClick={() => onReviewJoin(j.action_id)}>Review</Button>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card
        title="Machines"
        variant={stale ? 'stale' : 'default'}
        aside={
          <div className="om-net-actions">
            {isOwner && m.mode !== 'off' && (
              <Button size="sm" variant="ghost" aria-pressed={showIps} onClick={() => { setShowIps(!showIps); onShowAddresses?.(!showIps); }}>
                {showIps ? 'Hide addresses' : 'Show addresses'}
              </Button>
            )}
            <Button size="sm" variant="primary" icon="plus" onClick={onAddDevice} disabled={!!stale}>Add a device</Button>
          </div>
        }
      >
        <Table caption="Machines on the mesh" hideCaption columns={columns} rows={rows} rowKey={(r) => r.key} />
      </Card>

      <Card title="Names" level={2}>
        <p className="om-net-muted">On your home network the box answers to these names. Away from home, signed-in devices use the mesh names.</p>
        <ul className="om-net-names">
          {m.names.lan.map((n) => <li key={n}><code>{n}</code> <span className="om-net-muted">home network</span></li>)}
          {m.names.mesh.map((n) => <li key={n}><code>{n}</code> <span className="om-net-muted">mesh</span></li>)}
        </ul>
      </Card>

      <Card title="App addresses" level={2}>
        {m.apps.length === 0 ? (
          <p className="om-net-muted">Apps with a web page get their own address here once installed.</p>
        ) : (
          <ul className="om-net-list">
            {m.apps.map((a) => (
              <li key={a.app_id}>
                <a href={a.lan} target="_blank" rel="noreferrer">{a.lan.replace(/^https?:\/\//, '')}</a>
                <span className="om-net-muted">also {a.lan_alias.replace(/^https?:\/\//, '')} · away: {a.mesh.replace(/^https?:\/\//, '')}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

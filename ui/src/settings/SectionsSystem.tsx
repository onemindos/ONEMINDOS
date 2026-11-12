// SPDX-License-Identifier: Apache-2.0
// Settings sections about the machines: Devices & nodes, Network & mesh, Storage, About.
import { useState } from 'react';
import { formatAgo, formatDay, formatIn, secondsSince } from '../lib/time';
import { BRAND } from '../components/BrandMark';
import { Button } from '../components/Button';
import { FreshnessPill, StatusPill } from '../components/StatusPill';
import { Meter } from '../components/Meter';
import type { Tone } from '../tokens/tokens';
import { formatGb, usageByCategory } from './logic';
import { Async, CallHint, Empty, Fact, Group, QrCode, Row, Rows, SectionHead, SetIcon, Switch } from './primitives';
import type { SectionProps } from './SectionsAccess';
import { CATEGORY_LABEL, DEPLOY_CLASS, NODE_ROLE, type NodeRole } from './taxonomy';
import type { AboutData, DevicesData, NetworkData, StorageData } from './types';

/* ---------- Devices & nodes ---------- */
export function DevicesSection({ data, now, onIntent, onRetry }: SectionProps<DevicesData>) {
  const [role, setRole] = useState<NodeRole>('worker');
  return (
    <>
      <SectionHead icon="nodes" title="Devices & nodes" lede="The machines that make up this OneMind. A new machine joins by scanning a code; the join waits in Approvals." />
      <Async value={data} label="nodes" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => (
          <>
            <ul className="om-set-roles" aria-label="Node roles">
              {(Object.keys(NODE_ROLE) as NodeRole[]).map((r) => (
                <li key={r} className="om-set-role">
                  <span className="om-set-role-count">{d.nodes.filter((n) => n.role === r).length}</span>
                  <span className="om-set-role-name">{NODE_ROLE[r].label}</span>
                  <span className="om-set-role-text">{NODE_ROLE[r].sentence}</span>
                </li>
              ))}
            </ul>
            <Group title={`Nodes (${d.nodes.length})`} description="Status comes from each node's heartbeat: stale after 30 s, offline after 2 min.">
              {d.nodes.length === 0 ? (
                <Empty icon="nodes" title="No nodes reported yet" command="onemind nodes list">
                  The hub itself should appear within 30 seconds of starting. If it does not, open About &amp; diagnostics.
                </Empty>
              ) : (
                <Rows label="Nodes">
                  {d.nodes.map((n) => (
                    <Row
                      key={n.node_id}
                      icon={n.role === 'leaf' ? 'radio' : 'nodes'}
                      title={
                        <>
                          {n.hostname} <StatusPill tone="neutral" label={NODE_ROLE[n.role].label} dot={false} />
                        </>
                      }
                      description={`${n.board} · ${n.arch} · ${n.role === 'leaf' ? 'adapters only' : `${n.apps} app${n.apps === 1 ? '' : 's'}`}`}
                      meta={n.status === 'online' ? undefined : `Last report ${formatAgo(secondsSince(n.last_seen, now))}; numbers on its page are not live.`}
                      trailing={<FreshnessPill state={n.status === 'online' ? 'live' : n.status} detail={n.status === 'online' ? undefined : formatAgo(secondsSince(n.last_seen, now))} />}
                    />
                  ))}
                </Rows>
              )}
            </Group>
            <Group title="Add a node" description="Install OneMind on the new machine, then scan this code from it or type the short code.">
              <div className="om-set-join">
                {d.join ? (
                  <>
                    <QrCode modules={d.join.qr} label={`Join code ${d.join.code}`} />
                    <div className="om-set-join-text">
                      <p className="om-set-code" aria-label={`Short code ${d.join.code.split('').join(' ')}`}>
                        {d.join.code}
                      </p>
                      <p className="om-hint">
                        Single use, joins as a <strong>{NODE_ROLE[d.join.role].label.toLowerCase()}</strong>, expires {formatIn(d.join.expires_at, now)}. The join appears in Approvals with what the machine is; you approve it with your passkey.
                      </p>
                      <pre className="om-code">onemind join {d.join.code}</pre>
                      <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'fabric.join_code.revoke', params: { code: d.join!.code }, mode: 'instant', title: 'Join code cancelled', call: 'DELETE /v1/fabric/join-codes/{code}' })}>
                        Cancel this code
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="om-set-join-text">
                    <fieldset className="om-segmented">
                      <legend className="om-visually-hidden">Role of the new node</legend>
                      {(['worker', 'leaf'] as NodeRole[]).map((r) => (
                        <label key={r} className={role === r ? 'om-seg-on' : undefined}>
                          <input type="radio" name="join-role" value={r} checked={role === r} onChange={() => setRole(r)} />
                          {NODE_ROLE[r].label}
                        </label>
                      ))}
                    </fieldset>
                    <p className="om-hint">{NODE_ROLE[role].sentence} A second hub (high availability) is not supported yet.</p>
                    <div>
                      <Button variant="primary" icon="qr" disabled={!live} onClick={() => onIntent({ type: 'fabric.join_code.create', params: { role }, mode: 'instant', title: 'Join code created', call: `onemind nodes add --role ${role}` })}>
                        Show a join code
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </Group>
          </>
        )}
      </Async>
      <CallHint calls={['GET /v1/nodes', 'onemind nodes add --role worker|leaf', 'GET /v1/fabric/join-requests/{id}', 'onemind nodes remove <node>   (a request: drain, then revoke identity)']} />
    </>
  );
}

/* ---------- Network & mesh ---------- */
const MESH: Record<NetworkData['mesh']['state'], { tone: Tone; label: string }> = {
  connected: { tone: 'ok', label: 'Connected' },
  degraded: { tone: 'warn', label: 'Degraded' },
  off: { tone: 'neutral', label: 'Off' },
};
const TIER: Record<'lan' | 'mesh' | 'public', { tone: Tone; label: string }> = {
  lan: { tone: 'neutral', label: 'Home network' },
  mesh: { tone: 'info', label: 'Your devices' },
  public: { tone: 'warn', label: 'Internet' },
};

export function NetworkSection({ data, now, onIntent, onRetry }: SectionProps<NetworkData>) {
  return (
    <>
      <SectionHead icon="globe" title="Network & mesh" lede="How your nodes reach each other, how you reach the box from outside, its names on your home network, and its certificates." />
      <Async value={data} label="network settings" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => (
          <>
            <div className="om-set-facts">
              <Fact label="Mesh between nodes" value={`${d.mesh.peersOnline} of ${d.mesh.peers} linked`} pill={<StatusPill {...MESH[d.mesh.state]} />} />
              <Fact label="Encryption" value={d.mesh.transport} />
              <Fact label="Remote access" value={d.remote.enabled ? 'On' : 'Off'} pill={<StatusPill tone={d.remote.enabled ? 'info' : 'neutral'} label={d.remote.enabled ? 'Your devices only' : 'Home network only'} dot={false} />} />
            </div>
            <Group title="Remote access" description="Reach the box from your phone away from home, over a private overlay network. No port is opened on your router.">
              <Rows label="Remote access">
                <Row
                  icon="link"
                  title="Remote access for your devices"
                  description="Turning it on is a request you approve. Exposing an app to the whole internet is always a separate request."
                  trailing={<Switch checked={d.remote.enabled} label="Remote access for your devices" disabled={!live} onToggle={() => onIntent({ type: 'remote.set', params: { enabled: !d.remote.enabled }, mode: 'request', title: d.remote.enabled ? 'Turn off remote access' : 'Turn on remote access', call: 'PUT /v1/remote' })} />}
                />
                {d.remote.exposed.map((a) => (
                  <Row
                    key={a.app_id}
                    icon="apps"
                    title={a.name}
                    description={a.tier === 'public' ? 'Anyone on the internet can reach its login page.' : a.tier === 'mesh' ? 'Reachable from your signed-in devices.' : 'Reachable on your home network.'}
                    trailing={<StatusPill {...TIER[a.tier]} dot={a.tier === 'public'} />}
                  />
                ))}
              </Rows>
            </Group>
            <Group title="Names on your home network">
              {d.lanNames.length === 0 ? (
                <Empty icon="globe" title="No names yet">The box announces itself once its first app is installed.</Empty>
              ) : (
                <Rows label="Names on your home network">
                  {d.lanNames.map((n) => (
                    <Row key={n.name} icon="globe" title={<code>{n.name}</code>} description={n.target} trailing={<StatusPill tone="neutral" label={n.kind === 'mdns' ? 'mDNS' : 'DNS'} dot={false} />} />
                  ))}
                </Rows>
              )}
            </Group>
            <Group title="Certificates" description="Your browser trusts the box after you install its certificate once (shown as a QR when you pair a phone).">
              <Rows label="Certificates">
                {d.certificates.map((c) => {
                  const days = (Date.parse(c.expires_at) - now) / 86_400_000;
                  const tone: Tone = days < 0 ? 'bad' : days < 14 ? 'warn' : 'ok';
                  return (
                    <Row
                      key={c.id}
                      icon="lock"
                      title={c.name}
                      description={`${c.issuer === 'box-ca' ? 'Signed by this box' : 'Public certificate (ACME)'} · covers ${c.covers}`}
                      trailing={<StatusPill tone={tone} label={days < 0 ? 'Expired' : `Renews ${formatIn(c.expires_at, now)}`} />}
                    />
                  );
                })}
              </Rows>
            </Group>
          </>
        )}
      </Async>
      <CallHint calls={['GET /v1/network', 'PUT /v1/remote   (a request)', 'onemind apps expose <app> --tier public   (a separate request)']} />
    </>
  );
}

/* ---------- Storage ---------- */
/** Storage is read-only today; `onIntent` is accepted for a uniform section API. */
export function StorageSection({ data, now, onRetry }: SectionProps<StorageData>) {
  return (
    <>
      <SectionHead icon="disk" title="Storage" lede="Disks on every node, their health, and which kinds of apps use the space." />
      <Async value={data} label="storage" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => {
          const parts = usageByCategory(d.apps);
          const total = parts.reduce((n, p) => n + p.gb, 0);
          return (
            <>
              <Group title="Disks">
                {d.disks.length === 0 ? (
                  <Empty icon="info" title="No disks reported">Disk facts come from each node's heartbeat.</Empty>
                ) : (
                  <ul className="om-set-cards om-set-disks" aria-label="Disks">
                    {d.disks.map((k) => (
                      <li key={k.id} className="om-set-disk">
                        <div className="om-set-disk-head">
                          <strong>{k.label}</strong>
                          <StatusPill tone={k.health === 'ok' ? 'ok' : k.health === 'warn' ? 'warn' : 'bad'} label={k.health === 'ok' ? 'Healthy' : k.health === 'warn' ? 'Check' : 'Failing'} />
                        </div>
                        <Meter label={`${k.node} · ${k.role}`} value={k.used_gb} max={k.total_gb} valueText={`${formatGb(k.used_gb)} of ${formatGb(k.total_gb)}`} stale={!live} />
                        <span className="om-set-meta">
                          {k.kind.toUpperCase()} · {k.encrypted ? 'encrypted' : 'not encrypted'}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Group>
              <Group title="Used by apps, by category" description="App data only; system files and snapshots are counted on the disks above.">
                {total === 0 ? (
                  <Empty icon="apps" title="No app data yet">Apps you install keep their data on the node they run on.</Empty>
                ) : (
                  <>
                    <div className="om-set-stack" role="img" aria-label={parts.map((p) => `${p.label} ${formatGb(p.gb)}`).join(', ')}>
                      {parts.map((p, i) => (
                        <span key={p.key} className="om-set-stack-part" data-i={i} style={{ flexGrow: p.gb }} />
                      ))}
                    </div>
                    <ul className="om-set-legend" aria-label="Legend">
                      {parts.map((p, i) => (
                        <li key={p.key}>
                          <span className="om-set-swatch" data-i={i} aria-hidden="true" />
                          {p.label} <span className="om-set-meta">{formatGb(p.gb)}</span>
                        </li>
                      ))}
                    </ul>
                    <Rows label="Largest apps">
                      {[...d.apps]
                        .sort((a, b) => b.used_gb - a.used_gb)
                        .slice(0, 5)
                        .map((a) => (
                          <Row
                            key={a.app_id}
                            icon="apps"
                            title={a.name}
                            description={CATEGORY_LABEL[a.category]}
                            trailing={
                              <span className="om-set-actions">
                                <StatusPill tone={DEPLOY_CLASS[a.deploy_class].tone} label={DEPLOY_CLASS[a.deploy_class].label} dot={false} />
                                <span className="om-set-num">{formatGb(a.used_gb)}</span>
                              </span>
                            }
                          />
                        ))}
                    </Rows>
                  </>
                )}
              </Group>
            </>
          );
        }}
      </Async>
      <CallHint calls={['GET /v1/nodes   (disk facts per node)', 'GET /v1/apps?fields=usage', 'onemind storage']} />
    </>
  );
}

/* ---------- About & diagnostics ---------- */
function uptime(s: number): string {
  const d = Math.floor(s / 86_400);
  const h = Math.floor((s % 86_400) / 3600);
  return d > 0 ? `${d} d ${h} h` : `${h} h ${Math.floor((s % 3600) / 60)} min`;
}

export function AboutSection({ data, now, onIntent, onRetry }: SectionProps<AboutData>) {
  return (
    <>
      <SectionHead icon="info" title="About & diagnostics" lede="What this box runs, and what to send when something is wrong." />
      <Async value={data} label="system facts" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => (
          <>
            <div className="om-set-facts">
              <Fact label="Name" value={d.box} />
              <Fact label={BRAND.name} value={d.version} />
              <Fact label="Base" value={d.base} />
              <Fact label="Up for" value={uptime(d.uptime_s)} />
            </div>
            <Group title="Core components" description="Part of OneMind: installed with the system, updated with it, never removed on their own." aside={<StatusPill tone="neutral" label={DEPLOY_CLASS.core.label} dot={false} />}>
              <Rows label="Core components">
                {d.components.map((c) => (
                  <Row key={c.name} icon="shield" title={c.name} description={c.version} trailing={<StatusPill tone={c.state} label={c.state === 'ok' ? 'Healthy' : c.state === 'warn' ? 'Degraded' : 'Down'} />} />
                ))}
              </Rows>
            </Group>
            <Group title="Diagnostics">
              <Rows label="Diagnostics">
                <Row
                  icon="download"
                  title="Diagnostic bundle"
                  description="Logs, versions and health checks from every node. Tokens, passwords, addresses and names are removed before it is written."
                  meta={d.lastBundle_at ? `Last made ${formatAgo(secondsSince(d.lastBundle_at, now))}` : 'Never made'}
                  trailing={
                    <Button size="sm" disabled={!live} onClick={() => onIntent({ type: 'diagnostics.bundle', params: {}, mode: 'instant', title: 'Diagnostic bundle is being prepared', call: 'onemind diagnostics bundle' })}>
                      <SetIcon name="download" size={18} />
                      Make bundle
                    </Button>
                  }
                />
                <Row icon="alert" title="Rescue console" description="If the apps layer is down, each node still serves a small console on your home network: health, logs, update and rollback." />
                <Row icon="info" title="Build" description={<code>{d.build}</code>} meta={`Facts as of ${formatDay(new Date(now).toISOString())}`} />
              </Rows>
            </Group>
          </>
        )}
      </Async>
      <CallHint calls={['GET /v1/instance', 'onemind status', 'onemind diagnostics bundle']} />
    </>
  );
}

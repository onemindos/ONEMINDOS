// SPDX-License-Identifier: Apache-2.0
// Built-in Home widgets and the typed app widget (PLUGIN-UI.md §2). Each one renders from
// data it is given; none fetches. Each has loading, error, empty and stale states.
import { useId, type ReactNode } from 'react';
import type { ActionSummary } from '../components/ApprovalCard';
import { actionTitle, equivalentCall, requesterPill } from '../components/ApprovalCard';
import { Button } from '../components/Button';
import { Meter } from '../components/Meter';
import { FreshnessPill, StatusPill } from '../components/StatusPill';
import { FRESHNESS_LABEL } from '../lib/freshness';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import type { Tone } from '../tokens/tokens';
import { formatUptime } from './greeting';
import type { WidgetInstance, WidgetSize } from './layout';
import { AppGlyph, StatusDot, appState, gb, nodeFreshness, pct, tempTone } from './parts';
import type { AppWidgetPayload, HomeApp, HomeData, HomeNode, Loadable } from './types';
import { WidgetFrame, type WidgetBodyState } from './WidgetFrame';

export interface HomeLinks {
  approvals: string;
  nodes: string;
  activity: string;
  backups: string;
  updates: string;
  mesh: string;
  apps: string;
  app: (id: string) => string;
  approval: (id: string) => string;
}

export const DEFAULT_LINKS: HomeLinks = {
  approvals: '#/approvals',
  nodes: '#/nodes',
  activity: '#/activity',
  backups: '#/backups',
  updates: '#/updates',
  mesh: '#/nodes',
  apps: '#/apps',
  app: (id) => `#/app/${encodeURIComponent(id)}`,
  approval: (id) => `#/approvals?highlight=${encodeURIComponent(id)}`,
};

export type CanDecide = { allowed: true } | { allowed: false; reason: string };

export interface WidgetContext {
  data: HomeData;
  now: number;
  hubLive: boolean;
  /** "2 min ago": age of the hub's last answer. */
  hubAgo: string;
  canDecide: CanDecide;
  onApprove?: (a: ActionSummary) => void;
  onDeny?: (a: ActionSummary) => void;
  /** Action ids with a decision in flight. */
  busy?: ReadonlySet<string>;
  links: HomeLinks;
  showSource: boolean;
}

const ROWS: Record<WidgetSize, number> = { S: 2, M: 4, L: 8 };
const ago = (iso: string | null | undefined, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : 'never');

function bodyState<T>(l: Loadable<T>): WidgetBodyState {
  if (l.state === 'loading') return { kind: 'loading' };
  if (l.state === 'error') return { kind: 'error', error: l.error, message: l.message };
  return { kind: 'ready' };
}

function hubStale(ctx: WidgetContext) {
  // The page banner already says when the hub last answered; each widget just marks itself.
  return ctx.hubLive ? null : { label: 'Last known', detail: '' };
}

/* ---------- System (contract §2 heartbeat) ---------- */

function NodeStats({ n, size, now }: { n: HomeNode; size: WidgetSize; now: number }) {
  const f = nodeFreshness(n, now);
  const stale = f !== 'live';
  const memUsed = n.mem_total_mb - n.mem_available_mb;
  const diskUsed = n.disk_total_gb - n.disk_free_gb;
  const cpu = typeof n.cpu_percent === 'number' && Number.isFinite(n.cpu_percent) ? Math.max(0, Math.min(100, n.cpu_percent)) : null;
  const temp = typeof n.temp_c === 'number' && Number.isFinite(n.temp_c) ? n.temp_c : null;
  if (size === 'S') {
    return (
      <dl className="omh-tiles">
        <div className="omh-tile">
          <dt>CPU</dt>
          <dd>{cpu === null ? <span className="omh-na">Not reported</span> : pct(cpu / 100)}</dd>
        </div>
        <div className="omh-tile">
          <dt>Memory</dt>
          <dd>{pct(memUsed / n.mem_total_mb)}</dd>
        </div>
        <div className="omh-tile">
          <dt>Storage</dt>
          <dd>{pct(diskUsed / n.disk_total_gb)}</dd>
        </div>
        <div className="omh-tile">
          <dt>Temp</dt>
          <dd>{temp === null ? <span className="omh-na">No sensor</span> : `${Math.round(temp)} °C`}</dd>
        </div>
      </dl>
    );
  }
  return (
    <div className="omh-node-stats">
      {cpu === null ? (
        <p className="omh-meter-na">
          <span>CPU</span>
          <span className="omh-na">Not reported by this node</span>
        </p>
      ) : (
        <Meter label="CPU" value={cpu} max={100} valueText={`${pct(cpu / 100)} of ${n.cpus} cores`} stale={stale} />
      )}
      <Meter label="Memory" value={memUsed} max={n.mem_total_mb} valueText={`${gb(memUsed)} of ${gb(n.mem_total_mb)}`} stale={stale} />
      <Meter label="Storage" value={diskUsed} max={n.disk_total_gb} valueText={`${Math.round(n.disk_free_gb)} GB free of ${Math.round(n.disk_total_gb)} GB`} stale={stale} />
      <dl className="omh-facts">
        <div>
          <dt>Temperature</dt>
          <dd>{temp === null ? <span className="omh-na">No sensor</span> : stale ? `${Math.round(temp)} °C` : <StatusPill tone={tempTone(temp)} label={`${Math.round(temp)} °C`} />}</dd>
        </div>
        <div>
          <dt>Up for</dt>
          <dd>{formatUptime(n.uptime_s)}</dd>
        </div>
        {size === 'L' && (
          <div>
            <dt>Machine</dt>
            <dd>
              {n.role === 'hub' ? 'Hub' : 'Node'} · {n.arch} · {n.cpus} cores
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

function SystemWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const l = ctx.data.nodes;
  const nodes = l.state === 'ready' ? l.data : [];
  const one = w.nodeId ? nodes.find((n) => n.node_id === w.nodeId) : undefined;
  const title = w.nodeId ? (one?.hostname ?? 'Node') : 'System';
  const common = { title, icon: 'nodes' as const, size: w.size, href: ctx.links.nodes, source: w.nodeId ? `GET /v1/nodes/${w.nodeId}` : 'GET /v1/nodes', showSource: ctx.showSource };

  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  if (w.nodeId && !one) return <WidgetFrame {...common} state={{ kind: 'empty', title: 'This node has left the fabric', body: 'Remove this widget, or add one for another node.' }} />;
  if (!nodes.length) return <WidgetFrame {...common} state={{ kind: 'empty', title: 'No nodes have reported yet', body: 'The hub lists a node after its first heartbeat.' }} />;

  if (one) {
    const f = nodeFreshness(one, ctx.now);
    const stale = hubStale(ctx) ?? (f === 'live' ? null : { label: FRESHNESS_LABEL[f], detail: `Last report ${ago(one.last_seen, ctx.now)}. The values below are that report, not live.` });
    return (
      <WidgetFrame {...common} stale={stale} aside={f === 'live' && ctx.hubLive ? <FreshnessPill state="live" /> : undefined}>
        <NodeStats n={one} size={w.size} now={ctx.now} />
      </WidgetFrame>
    );
  }

  const online = nodes.filter((n) => nodeFreshness(n, ctx.now) === 'live').length;
  return (
    <WidgetFrame {...common} stale={hubStale(ctx)} aside={<StatusPill tone={online === nodes.length ? 'ok' : 'warn'} label={`${online} of ${nodes.length} online`} />}>
      <ul className="omh-node-list">
        {nodes.slice(0, w.size === 'S' ? 3 : ROWS[w.size]).map((n) => {
          const f = nodeFreshness(n, ctx.now);
          const memF = (n.mem_total_mb - n.mem_available_mb) / n.mem_total_mb;
          const diskF = (n.disk_total_gb - n.disk_free_gb) / n.disk_total_gb;
          const cpu = typeof n.cpu_percent === 'number' ? n.cpu_percent / 100 : null;
          return (
            <li key={n.node_id} className={f === 'live' ? undefined : 'omh-row-stale'}>
              <span className="omh-node-name">
                <StatusDot tone={f === 'live' ? 'ok' : f === 'stale' ? 'warn' : 'neutral'} hollow={f !== 'live'} />
                <span>{n.hostname}</span>
                {f !== 'live' && <span className="omh-row-note">{FRESHNESS_LABEL[f]} · {ago(n.last_seen, ctx.now)}</span>}
              </span>
              {w.size !== 'S' && (
                <span className="omh-node-nums">
                  <span>
                    <span className="omh-num-label">CPU</span> {cpu === null ? '—' : pct(cpu)}
                    {cpu === null && <span className="om-visually-hidden"> not reported</span>}
                  </span>
                  <span>
                    <span className="omh-num-label">Mem</span> {pct(memF)}
                  </span>
                  <span>
                    <span className="omh-num-label">Disk</span> {pct(diskF)}
                  </span>
                  {w.size === 'L' && (
                    <span>
                      <span className="omh-num-label">Temp</span> {typeof n.temp_c === 'number' ? `${Math.round(n.temp_c)} °C` : '—'}
                    </span>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </WidgetFrame>
  );
}

/* ---------- Needs you (contract §3 actions) ---------- */

function ApprovalRow({ a, ctx, compact }: { a: ActionSummary; ctx: WidgetContext; compact: boolean }) {
  const reasonId = useId();
  const who = a.requested_by ? requesterPill(a.requested_by) : { tone: 'neutral' as Tone, label: 'Unknown' };
  const blocked = !ctx.hubLive ? 'The hub is not answering. Decide when it is back.' : !ctx.canDecide.allowed ? ctx.canDecide.reason : null;
  const busy = ctx.busy?.has(a.id) ?? false;
  const expires = formatIn(a.expires_at, ctx.now);
  return (
    <li className="omh-approval">
      <div className="omh-approval-main">
        <StatusPill tone={who.tone} label={who.label} dot={false} />
        <a className="omh-approval-title" href={ctx.links.approval(a.id)}>
          {actionTitle(a)}
        </a>
        <span className={expires === 'expired' ? 'omh-expiry omh-expired' : 'omh-expiry'}>{expires === 'expired' ? 'Expired' : `Expires ${expires}`}</span>
      </div>
      {!compact && a.reason && <p className="omh-approval-reason">“{a.reason}”</p>}
      <div className="omh-approval-actions">
        <Button size="sm" variant="primary" icon="check" busy={busy} disabled={!!blocked || expires === 'expired'} aria-describedby={blocked ? reasonId : undefined} onClick={() => ctx.onApprove?.(a)} title={equivalentCall(a, 'approve')}>
          Approve
        </Button>
        <Button size="sm" variant="ghost" disabled={!!blocked || busy || expires === 'expired'} aria-describedby={blocked ? reasonId : undefined} onClick={() => ctx.onDeny?.(a)} title={equivalentCall(a, 'deny')}>
          Deny
        </Button>
        {blocked && (
          <span id={reasonId} className="omh-blocked">
            {blocked}
          </span>
        )}
      </div>
    </li>
  );
}

function ApprovalsWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const l = ctx.data.approvals;
  const list = l.state === 'ready' ? l.data.filter((a) => a.state === 'awaiting_approval') : [];
  const max = w.size === 'S' ? 1 : w.size === 'M' ? 2 : 4;
  const common = { title: 'Needs you', icon: 'approvals' as const, size: w.size, href: ctx.links.approvals, hrefLabel: 'All', source: 'GET /v1/actions?state=awaiting_approval', showSource: ctx.showSource };
  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  if (!list.length)
    return (
      <WidgetFrame {...common} stale={hubStale(ctx)} state={{ kind: 'empty', title: 'Nothing needs you', body: 'Requests from people, agents and the system wait here until you decide.' }} />
    );
  const more = list.length - max;
  return (
    <WidgetFrame {...common} stale={hubStale(ctx)} aside={<StatusPill tone="warn" label={`${list.length} waiting`} />}>
      <ul className="omh-approvals">
        {list.slice(0, max).map((a) => (
          <ApprovalRow key={a.id} a={a} ctx={ctx} compact={w.size === 'S'} />
        ))}
      </ul>
      {more > 0 && (
        <a className="omh-more" href={ctx.links.approvals}>
          {more} more waiting
        </a>
      )}
    </WidgetFrame>
  );
}

/* ---------- Activity (audit log, PROPOSED read endpoint) ---------- */

const ACTOR_TONE = { person: 'neutral', agent: 'agent', system: 'info' } as const;

function ActivityWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const l = ctx.data.activity;
  const common = { title: 'Recent activity', icon: 'activity' as const, size: w.size, href: ctx.links.activity, hrefLabel: 'Timeline', source: 'GET /v1/audit?limit=8 (proposed)', showSource: ctx.showSource };
  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  if (!l.data.length) return <WidgetFrame {...common} state={{ kind: 'empty', title: 'Nothing has happened yet', body: 'Installs, decisions and updates appear here with who did them.' }} />;
  return (
    <WidgetFrame {...common} stale={hubStale(ctx)}>
      <ol className="omh-feed">
        {l.data.slice(0, w.size === 'S' ? 3 : w.size === 'M' ? 5 : 8).map((e) => (
          <li key={e.seq}>
            <time className="omh-time" dateTime={e.at}>
              {ago(e.at, ctx.now)}
            </time>
            <span className="omh-feed-text">
              <StatusPill tone={ACTOR_TONE[e.actor.kind]} label={e.actor.name} dot={false} /> {e.text}
            </span>
            {e.result && w.size !== 'S' && <StatusPill tone={e.result.tone} label={e.result.label} />}
          </li>
        ))}
      </ol>
    </WidgetFrame>
  );
}

/* ---------- Backups (PROPOSED, BAK-B1) ---------- */

const DEST: Record<'ok' | 'behind' | 'failing', { tone: Tone; label: string }> = {
  ok: { tone: 'ok', label: 'Current' },
  behind: { tone: 'warn', label: 'Behind' },
  failing: { tone: 'bad', label: 'Failing' },
};

function BackupsWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const l = ctx.data.backups;
  const common = { title: 'Backups', icon: 'backups' as const, size: w.size, href: ctx.links.backups, source: 'GET /v1/backups/status (proposed)', showSource: ctx.showSource };
  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  const b = l.data;
  if (!b.destinations.length && !b.last_run)
    return <WidgetFrame {...common} state={{ kind: 'empty', title: 'No backups set up', body: 'Add a USB disk, another OneMind or a bucket in Backups.' }} />;
  const runAge = b.last_run ? secondsSince(b.last_run, ctx.now) : Number.POSITIVE_INFINITY;
  const runTone: Tone = runAge > 26 * 3600 ? 'warn' : 'ok';
  const verifyAge = b.last_verified_restore ? secondsSince(b.last_verified_restore, ctx.now) : Number.POSITIVE_INFINITY;
  const verifyTone: Tone = verifyAge > 8 * 86_400 ? 'warn' : 'ok';
  return (
    <WidgetFrame {...common} stale={hubStale(ctx)}>
      <dl className="omh-facts omh-facts-big">
        <div>
          <dt>Last backup</dt>
          <dd>{ctx.hubLive ? <StatusPill tone={runTone} label={ago(b.last_run, ctx.now)} /> : ago(b.last_run, ctx.now)}</dd>
        </div>
        <div>
          <dt>Restore verified</dt>
          <dd>{ctx.hubLive ? <StatusPill tone={verifyTone} label={ago(b.last_verified_restore, ctx.now)} /> : ago(b.last_verified_restore, ctx.now)}</dd>
        </div>
      </dl>
      {w.size !== 'S' && (
        <ul className="omh-rows">
          {b.destinations.slice(0, ROWS[w.size]).map((d) => (
            <li key={d.name}>
              <span className="omh-row-main">{d.name}</span>
              <span className="omh-time">{ago(d.last_success, ctx.now)}</span>
              <StatusPill tone={DEST[d.state].tone} label={DEST[d.state].label} />
            </li>
          ))}
        </ul>
      )}
    </WidgetFrame>
  );
}

/* ---------- Updates (PROPOSED, OSU-P1) ---------- */

function UpdatesWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const l = ctx.data.updates;
  const common = { title: 'Updates', icon: 'updates' as const, size: w.size, href: ctx.links.updates, hrefLabel: 'Review', source: 'GET /v1/updates (proposed)', showSource: ctx.showSource };
  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  const u = l.data;
  const checkAge = secondsSince(u.checked_at, ctx.now);
  const oldCheck = checkAge > 2 * 86_400 ? { label: 'Old check', detail: `Last checked ${ago(u.checked_at, ctx.now)}; there may be newer updates.` } : null;
  const count = (u.os ? 1 : 0) + u.apps.length;
  if (!count) return <WidgetFrame {...common} stale={hubStale(ctx) ?? oldCheck} state={{ kind: 'empty', title: 'Everything is up to date', body: `Checked ${ago(u.checked_at, ctx.now)}.` }} />;
  const appName = (id: string) => (ctx.data.apps.state === 'ready' ? ctx.data.apps.data.find((a) => a.id === id)?.name : undefined) ?? id;
  return (
    <WidgetFrame {...common} stale={hubStale(ctx) ?? oldCheck} aside={<StatusPill tone="info" label={`${count} available`} />}>
      <ul className="omh-rows">
        {u.os && (
          <li>
            <span className="omh-row-main">
              <strong>OneMind OS</strong> {u.os.from} → {u.os.to}
            </span>
            {u.os.channel === 'security' && <StatusPill tone="warn" label="Security" />}
          </li>
        )}
        {u.apps.slice(0, w.size === 'S' ? 1 : ROWS[w.size]).map((a) => (
          <li key={a.app_id}>
            <span className="omh-row-main">
              {appName(a.app_id)} <span className="omh-ver">{a.to}</span>
            </span>
          </li>
        ))}
      </ul>
      {w.size === 'S' && u.apps.length > 1 && <p className="om-hint">and {u.apps.length - 1} more</p>}
    </WidgetFrame>
  );
}

/* ---------- Mesh and network (PROPOSED, FAB-P1) ---------- */

const LINK: Record<'up' | 'degraded' | 'down', { tone: Tone; label: string }> = {
  up: { tone: 'ok', label: 'Up' },
  degraded: { tone: 'warn', label: 'Slow' },
  down: { tone: 'bad', label: 'Down' },
};
const VIA = { lan: 'Home network', mesh: 'Mesh', leaf: 'Leaf link' };
const REMOTE = { off: 'Remote access is off', mesh: 'Reachable on your mesh', public: 'Reachable from the internet' };

function MeshWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const l = ctx.data.mesh;
  const common = { title: 'Network', icon: 'link' as const, size: w.size, href: ctx.links.mesh, source: 'GET /v1/fabric/links (proposed)', showSource: ctx.showSource };
  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  const m = l.data;
  if (!m.links.length) return <WidgetFrame {...common} state={{ kind: 'empty', title: 'Only the hub so far', body: 'Add a node to see its link here.' }} />;
  const up = m.links.filter((x) => x.state === 'up').length;
  return (
    <WidgetFrame {...common} stale={hubStale(ctx)} aside={<StatusPill tone={up === m.links.length ? 'ok' : 'warn'} label={`${up} of ${m.links.length} up`} />}>
      {w.size !== 'S' ? (
        <ul className="omh-rows">
          {m.links.slice(0, ROWS[w.size]).map((x) => (
            <li key={x.hostname}>
              <span className="omh-row-main">
                {x.hostname} <span className="omh-row-note">{VIA[x.via]}</span>
              </span>
              {x.rtt_ms != null && x.state !== 'down' && <span className="omh-time">{Math.round(x.rtt_ms)} ms</span>}
              <StatusPill tone={LINK[x.state].tone} label={LINK[x.state].label} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="omh-big">{up === m.links.length ? 'All links up' : `${m.links.length - up} ${m.links.length - up === 1 ? 'link needs' : 'links need'} a look`}</p>
      )}
      <p className="omh-foot">
        <StatusPill tone={m.remote_access === 'public' ? 'warn' : 'neutral'} label={REMOTE[m.remote_access]} dot={false} />
      </p>
    </WidgetFrame>
  );
}

/* ---------- App widget (typed templates, PLUGIN-UI.md §2) ---------- */

function Payload({ p, size, now }: { p: AppWidgetPayload; size: WidgetSize; now: number }) {
  switch (p.template) {
    case 'stat':
      return (
        <p className="omh-stat">
          <span className={p.tone ? `omh-stat-value om-tone-${p.tone} omh-tinted` : 'omh-stat-value'}>
            {p.value}
            {p.unit && <span className="omh-stat-unit"> {p.unit}</span>}
          </span>
          <span className="omh-stat-label">{p.label}</span>
        </p>
      );
    case 'stats':
      return (
        <dl className="omh-tiles">
          {p.items.slice(0, 4).map((s) => (
            <div className="omh-tile" key={s.label}>
              <dt>{s.label}</dt>
              <dd>{s.value}</dd>
            </div>
          ))}
        </dl>
      );
    case 'list':
      return (
        <ul className="omh-rows">
          {p.items.slice(0, size === 'S' ? 2 : 5).map((it, i) => (
            <li key={i}>
              <span className="omh-row-main">
                {it.text}
                {it.detail && <span className="omh-row-note"> {it.detail}</span>}
              </span>
              {it.at && <span className="omh-time">{ago(it.at, now)}</span>}
            </li>
          ))}
        </ul>
      );
    case 'progress':
      // Progress is not resource use: a nearly full bar is good news, so it never turns amber or red.
      return <Meter label={p.label} value={p.value} max={p.max} valueText={p.text} warnAt={2} badAt={2} />;
    case 'status':
      return (
        <div className="omh-status">
          <StatusPill tone={p.tone} label={p.label} />
          {p.detail && <p className="om-hint">{p.detail}</p>}
        </div>
      );
  }
}

function AppWidget({ w, ctx }: { w: WidgetInstance; ctx: WidgetContext }) {
  const apps = ctx.data.apps.state === 'ready' ? ctx.data.apps.data : [];
  const app = apps.find((a) => a.id === w.appId);
  const decl = app?.widgets?.find((d) => d.id === w.widgetId);
  const glyph = app ? <AppGlyph app={app} size={20} /> : undefined;
  const title = app && decl ? `${app.name} · ${decl.title}` : `App widget (${w.appId ?? 'unknown'})`;
  const common = { title, icon: 'apps' as const, glyph, size: w.size, href: app ? ctx.links.app(app.id) : undefined, source: decl ? `GET /v1/apps/${app!.id}/widgets/${decl.id} (proposed)` : undefined, showSource: ctx.showSource };
  if (ctx.data.apps.state !== 'ready') return <WidgetFrame {...common} state={bodyState(ctx.data.apps)} />;
  if (!app || !app.installed) return <WidgetFrame {...common} state={{ kind: 'empty', title: 'This app is no longer installed', body: 'Remove this widget from Home.' }} />;
  if (!decl) return <WidgetFrame {...common} state={{ kind: 'empty', title: 'The app no longer offers this widget', body: 'Its new version dropped it. Remove this widget.' }} />;
  const l = ctx.data.appWidgets[`${app.id}/${decl.id}`] ?? { state: 'loading' as const };
  if (l.state !== 'ready') return <WidgetFrame {...common} state={bodyState(l)} />;
  if (l.data.template !== decl.template)
    return <WidgetFrame {...common} state={{ kind: 'error', error: 'template_mismatch', message: `The app sent a ${l.data.template} payload for a ${decl.template} widget, so it is not shown.` }} />;
  const age = secondsSince(l.data.updated_at, ctx.now);
  const st = appState(app, ctx.hubLive);
  const stale =
    hubStale(ctx) ??
    (app.status !== 'running'
      ? { label: st.label, detail: `${app.name} is not running. This is its last report, from ${formatAgo(age)}.` }
      : !(age <= 2 * decl.source.refreshSeconds)
        ? { label: 'Stale', detail: `Last update ${formatAgo(age)}; it should refresh every ${decl.source.refreshSeconds} s.` }
        : null);
  return (
    <WidgetFrame {...common} stale={stale}>
      <Payload p={l.data} size={w.size} now={ctx.now} />
    </WidgetFrame>
  );
}

/* ---------- dispatcher ---------- */

export const WIDGET_META: Record<Exclude<WidgetInstance['kind'], 'app'>, { title: string; icon: 'approvals' | 'nodes' | 'activity' | 'backups' | 'updates' | 'link'; blurb: string }> = {
  approvals: { title: 'Needs you', icon: 'approvals', blurb: 'Requests waiting for your decision. Always first.' },
  system: { title: 'System', icon: 'nodes', blurb: 'CPU, memory, storage, temperature and uptime from each heartbeat.' },
  activity: { title: 'Recent activity', icon: 'activity', blurb: 'What happened and who did it.' },
  backups: { title: 'Backups', icon: 'backups', blurb: 'Last backup, last verified restore, destinations.' },
  updates: { title: 'Updates', icon: 'updates', blurb: 'OS and app updates waiting for you.' },
  mesh: { title: 'Network', icon: 'link', blurb: 'Links between your nodes and remote access.' },
};

export function renderWidget(w: WidgetInstance, ctx: WidgetContext): ReactNode {
  switch (w.kind) {
    case 'approvals':
      return <ApprovalsWidget w={w} ctx={ctx} />;
    case 'system':
      return <SystemWidget w={w} ctx={ctx} />;
    case 'activity':
      return <ActivityWidget w={w} ctx={ctx} />;
    case 'backups':
      return <BackupsWidget w={w} ctx={ctx} />;
    case 'updates':
      return <UpdatesWidget w={w} ctx={ctx} />;
    case 'mesh':
      return <MeshWidget w={w} ctx={ctx} />;
    case 'app':
      return <AppWidget w={w} ctx={ctx} />;
  }
}

/** Accessible name of a widget instance, for move/resize announcements. */
export function widgetName(w: WidgetInstance, data: HomeData): string {
  if (w.kind === 'app') {
    const app: HomeApp | undefined = data.apps.state === 'ready' ? data.apps.data.find((a) => a.id === w.appId) : undefined;
    const d = app?.widgets?.find((x) => x.id === w.widgetId);
    return app && d ? `${app.name} ${d.title}` : `App widget (${w.appId ?? 'unknown'})`;
  }
  if (w.kind === 'system' && w.nodeId) {
    const n = data.nodes.state === 'ready' ? data.nodes.data.find((x) => x.node_id === w.nodeId) : undefined;
    return `System, ${n?.hostname ?? 'node'}`;
  }
  return WIDGET_META[w.kind].title;
}

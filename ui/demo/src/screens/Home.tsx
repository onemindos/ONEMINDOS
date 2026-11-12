// SPDX-License-Identifier: Apache-2.0
// Home: "is everything fine, and does anything need me?" (IA §2.1)
import { ApprovalCard, Button, Card, Icon, Meter, PageHeader, StatusPill, formatAgo, secondsSince } from '../../../src';
import { ACTOR_TONE, AppIcon, Section, Stat } from '../bits';
import { NOW, activity, alerts, apps, backup, nodes, pending } from '../fixtures';

export function Home() {
  const online = nodes.filter((n) => n.status === 'online').length;
  const installed = apps.filter((a) => a.installed);
  const open = alerts.filter((a) => !a.acked);
  return (
    <>
      <PageHeader title="Good afternoon" lede="3 requests need your decision. Everything else is running." />
      <div className="d-stats">
        <Stat label="Nodes" value={`${online} of ${nodes.length}`} detail="1 stale · 1 offline" tone="warn" href="#/nodes" />
        <Stat label="Apps" value={`${installed.length} running`} detail="All healthy" tone="ok" href="#/apps" />
        <Stat label="Approvals" value={`${pending.length} waiting`} detail="1 expires in 40 min" tone="warn" href="#/approvals" />
        <Stat label="Last backup" value={formatAgo(secondsSince(backup.lastRun, NOW))} detail={`Restore verified ${formatAgo(secondsSince(backup.lastVerifiedRestore, NOW))}`} tone="ok" href="#/backups" />
      </div>

      <Section title="Needs you" aside={<a href="#/approvals">All approvals</a>}>
        <div className="d-grid">
          {pending.slice(0, 2).map((a) => (
            <ApprovalCard key={a.id} action={a} now={NOW} canDecide={{ allowed: true }} onApprove={() => {}} onDeny={() => {}} />
          ))}
          {open.slice(0, 1).map((al) => (
            <Card key={al.id} level={3} title={al.title} variant="attention" aside={<StatusPill tone="warn" label="Warning" />} footer={<Button size="sm" icon="chevron">Open alert</Button>}>
              <p className="om-hint">{al.body}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Apps" aside={<a href="#/apps">Market</a>}>
        <ul className="d-tiles">
          {installed.map((a) => (
            <li key={a.id}>
              <a className="d-tile" href={`#/app/${a.id}`}>
                <AppIcon app={a} size={56} />
                {a.name}
                <span className="d-tile-state">{a.status === 'running' ? 'Running' : a.status}</span>
              </a>
            </li>
          ))}
          <li>
            <a className="d-tile" href="#/apps">
              <span className="d-appicon d-hue-neutral" style={{ width: 56, height: 56 }} aria-hidden="true">
                <Icon name="plus" />
              </span>
              Add app
            </a>
          </li>
        </ul>
      </Section>

      <Section title="Widgets from your apps" aside={<span className="om-hint">Declared in each app's manifest</span>}>
        <div className="d-widgets">
          <div className="d-widget">
            <div className="d-widget-head">
              <AppIcon app={apps[2]!} size={22} /> Uptime Kuma · monitors
            </div>
            <span className="d-widget-num">12 / 12</span>
            <StatusPill tone="ok" label="All up" detail="checked 20 s ago" />
          </div>
          <div className="d-widget">
            <div className="d-widget-head">
              <AppIcon app={apps[1]!} size={22} /> ntfy · last messages
            </div>
            <ul className="d-list">
              <li><span className="d-list-main">Backup finished</span><span className="d-time">41 min ago</span></li>
              <li><span className="d-list-main">Garage door left open</span><span className="d-time">3 h ago</span></li>
            </ul>
          </div>
          <div className="d-widget">
            <div className="d-widget-head">
              <Icon name="nodes" size={18} /> home-hub · storage
            </div>
            <Meter label="Data disk" value={125} max={477} valueText="352 GB free of 477 GB" />
            <Meter label="Memory" value={6.8} max={16} valueText="6.8 of 16 GB used" />
          </div>
        </div>
      </Section>

      <Section title="Recent activity" aside={<a href="#/activity">Full timeline</a>}>
        <Card>
          <ul className="d-list">
            {activity.slice(0, 5).map((e) => (
              <li key={e.seq}>
                <span className="d-time">{formatAgo(secondsSince(e.at, NOW))}</span>
                <span className="d-list-main">
                  <StatusPill tone={ACTOR_TONE[e.kind]} label={e.actor} dot={false} /> {e.text}
                </span>
                {e.result && <StatusPill tone={e.result} label={e.resultLabel ?? ''} />}
              </li>
            ))}
          </ul>
        </Card>
      </Section>
    </>
  );
}

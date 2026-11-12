// SPDX-License-Identifier: Apache-2.0
// Alerts and notifications (IA §2.9): one inbox, repairs with fix actions, and routing.
import { Button, Card, PageHeader, StatusPill, Table, formatAgo, secondsSince } from '../../../src';
import { Section } from '../bits';
import { NOW, alerts } from '../fixtures';

const SEV = { critical: ['bad', 'Critical'], warning: ['warn', 'Warning'], info: ['info', 'Info'] } as const;

export function Notifications() {
  return (
    <>
      <PageHeader title="Alerts" lede="One inbox for the whole fabric. Each alert says what happened, what it affects and what you can do." />
      <Section title="Open">
        <div className="d-stack">
          {alerts.map((a) => (
            <Card
              key={a.id}
              level={3}
              title={a.title}
              subtitle={`${a.source} · ${formatAgo(secondsSince(a.created, NOW))}${a.acked ? ' · acknowledged' : ''}`}
              variant={a.acked ? 'default' : 'attention'}
              aside={<StatusPill tone={SEV[a.severity][0]} label={SEV[a.severity][1]} />}
              footer={
                <div className="d-row">
                  {a.actionId && <Button size="sm" variant="primary" icon="approvals">Review request</Button>}
                  {a.fix && <Button size="sm" variant="primary">{a.fix}…</Button>}
                  {!a.acked && <Button size="sm">Acknowledge</Button>}
                  <Button size="sm" variant="ghost">Resolve</Button>
                </div>
              }
            >
              <p className="om-hint">{a.body}</p>
              {a.fix && <p className="om-hint">The fix is a request: it goes to Approvals like any other change.</p>}
            </Card>
          ))}
        </div>
      </Section>
      <div className="d-grid-2">
        <Section title="Where alerts go">
          <Table
            caption="Delivery channels"
            hideCaption
            rowKey={(r) => r.ch}
            columns={[
              { key: 'ch', header: 'Channel', render: (r) => <strong>{r.ch}</strong> },
              { key: 'detail', header: 'How', secondary: true },
              { key: 'st', header: 'State', render: (r) => <StatusPill tone={r.tone} label={r.st} /> },
            ]}
            rows={[
              { ch: 'This dashboard', detail: 'Always on', st: 'On', tone: 'ok' as const },
              { ch: 'Android phone', detail: 'UnifiedPush through ntfy on this box', st: 'On', tone: 'ok' as const },
              { ch: 'iPhone', detail: 'Empty ping through the relay; the phone fetches the alert from this box', st: 'On', tone: 'ok' as const },
              { ch: 'Email', detail: 'Not set up', st: 'Off', tone: 'neutral' as const },
              { ch: 'Matrix / Telegram', detail: 'Not set up', st: 'Off', tone: 'neutral' as const },
            ]}
          />
        </Section>
        <Section title="Rules">
          <Card>
            <ul className="d-list">
              <li><span className="d-list-main"><strong>Critical</strong> → all channels, any time</span></li>
              <li><span className="d-list-main"><strong>Approval waiting</strong> → phone, with Approve / Deny buttons</span></li>
              <li><span className="d-list-main"><strong>Warning</strong> → phone, not 22:00–07:00</span></li>
              <li><span className="d-list-main"><strong>Info</strong> → this dashboard only</span></li>
            </ul>
            <p className="om-hint">Repeats of the same alert within 1 hour are grouped.</p>
          </Card>
        </Section>
      </div>
    </>
  );
}

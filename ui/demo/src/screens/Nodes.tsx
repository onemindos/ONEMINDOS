// SPDX-License-Identifier: Apache-2.0
// Nodes and fabric (IA §2.6): every machine, honest freshness, add/remove through approval.
import { Button, Card, NodeCard, PageHeader, StatusPill, Table } from '../../../src';
import { Section } from '../bits';
import { NOW, nodes } from '../fixtures';

export function Nodes() {
  return (
    <>
      <PageHeader
        title="Nodes"
        lede="Every machine in this OneMind. A node that stops reporting is shown as stale after 30 seconds and offline after 2 minutes, never as live."
        actions={<Button variant="primary" icon="qr">Add a node</Button>}
      />
      <div className="d-grid">
        {nodes.map((n) => (
          <NodeCard
            key={n.node_id}
            node={n}
            now={NOW}
            actions={
              <div className="d-row">
                <Button size="sm">Details</Button>
                {n.role !== 'hub' && <Button size="sm" variant="ghost">{n.status === 'offline' ? 'Remove…' : 'Drain…'}</Button>}
              </div>
            }
          />
        ))}
        <Card level={3} title="Add a node" subtitle="Scan with the OneMind app, or run one command on the new machine" variant="sunken">
          <div className="d-row" style={{ alignItems: 'flex-start' }}>
            <span className="d-qr" role="img" aria-label="Join code (placeholder in this demo)" />
            <div className="d-stack" style={{ flex: 1, minWidth: 180 }}>
              <p className="om-hint">The code works once and expires in 60 minutes. The new node appears in Approvals before it can run anything.</p>
              <pre className="om-code">onemind node join</pre>
              <p className="om-hint">Planned command (backlog FAB-P1).</p>
            </div>
          </div>
        </Card>
      </div>
      <Section title="Fabric links">
        <Table
          caption="Bus links between nodes"
          hideCaption
          rowKey={(r) => r.from}
          columns={[
            { key: 'from', header: 'Node' },
            { key: 'link', header: 'Link to hub' },
            { key: 'auth', header: 'Identity', secondary: true },
            { key: 'state', header: 'State', render: (r) => <StatusPill tone={r.tone} label={r.state} /> },
          ]}
          rows={[
            { from: 'pi-garage', link: 'Bus leaf, TLS', auth: 'Node account', state: 'Connected', tone: 'ok' as const },
            { from: 'office-laptop', link: 'Bus leaf, TLS', auth: 'Node account', state: 'No traffic for 75 s', tone: 'warn' as const },
            { from: 'cloud-relay', link: 'Bus leaf over overlay network', auth: 'Node account', state: 'Disconnected 3 h', tone: 'neutral' as const },
          ]}
        />
      </Section>
    </>
  );
}

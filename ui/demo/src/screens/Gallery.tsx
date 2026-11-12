// SPDX-License-Identifier: Apache-2.0
// Visual test page: every component in each state, plus the token swatches.
import { useState } from 'react';
import { ApprovalCard, Button, Card, Dialog, EmptyState, ICON_NAMES, Icon, Meter, NodeCard, PageHeader, StatusPill, TONES, Table, TrustCard, light, useToast } from '../../../src';
import { Section } from '../bits';
import { NOW, apps, decided, nodes, pending } from '../fixtures';

const ROLES = Object.keys(light).filter((k) => !TONES.some((t) => k.startsWith(`${t}-`)));

export function Gallery() {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  return (
    <>
      <PageHeader title="Components" lede="Every component and state, for visual review in light and dark. No Storybook needed." />
      <Section title="Colour roles">
        <div className="d-swatches">
          {ROLES.map((r) => (
            <div className="d-swatch" key={r}>
              <div className="d-swatch-chip" style={{ background: `var(--om-color-${r})` }} />
              <span>{r}</span>
            </div>
          ))}
        </div>
      </Section>
      <Section title="Status pills">
        <div className="d-row">
          {TONES.map((t) => (
            <StatusPill key={t} tone={t} label={t} />
          ))}
          <StatusPill tone="info" label="Running" pulse />
          <StatusPill tone="warn" label="Stale" detail="last seen 75 s ago" />
        </div>
      </Section>
      <Section title="Buttons">
        <div className="d-row">
          <Button variant="primary" icon="check">Approve</Button>
          <Button>Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Remove</Button>
          <Button variant="primary" busy>Busy</Button>
          <Button disabled>Disabled</Button>
          <Button size="sm">Small</Button>
        </div>
      </Section>
      <Section title="Icons">
        <div className="d-row">
          {ICON_NAMES.map((n) => (
            <span key={n} title={n} className="d-row" style={{ gap: 4, fontSize: 12, color: 'var(--om-color-text-muted)' }}>
              <Icon name={n} /> {n}
            </span>
          ))}
        </div>
      </Section>
      <Section title="Cards">
        <div className="d-grid">
          <Card title="Default" subtitle="Subtitle" aside={<StatusPill tone="ok" label="Good" />}>Body text.</Card>
          <Card title="Attention" variant="attention">Needs a decision.</Card>
          <Card title="Stale" variant="stale">Last report, not live.</Card>
          <Card title="Sunken" variant="sunken">Secondary content.</Card>
        </div>
      </Section>
      <Section title="Meters">
        <Card>
          <Meter label="Fine" value={30} max={100} valueText="30%" />
          <Meter label="Warn" value={85} max={100} valueText="85%" />
          <Meter label="Bad" value={96} max={100} valueText="96%" />
          <Meter label="Stale" value={50} max={100} valueText="50% (last report)" stale />
        </Card>
      </Section>
      <Section title="Approval cards">
        <div className="d-grid">
          <ApprovalCard action={pending[0]!} now={NOW} canDecide={{ allowed: true }} onApprove={() => {}} onDeny={() => {}} />
          <ApprovalCard action={pending[0]!} now={NOW} canDecide={{ allowed: false, reason: 'Only the owner can approve.' }} onApprove={() => {}} />
          <ApprovalCard action={{ ...pending[1]!, expires_at: new Date(NOW - 1000).toISOString() }} now={NOW} canDecide={{ allowed: true }} onApprove={() => {}} />
          <ApprovalCard action={{ ...pending[0]!, state: 'dispatched' }} now={NOW} canDecide={{ allowed: true }} />
          <ApprovalCard action={decided[0]!} now={NOW} canDecide={{ allowed: true }} />
          <ApprovalCard action={decided[2]!} now={NOW} canDecide={{ allowed: true }} />
        </div>
      </Section>
      <Section title="Node cards">
        <div className="d-grid">
          {nodes.map((n) => (
            <NodeCard key={n.node_id} node={n} now={NOW} />
          ))}
        </div>
      </Section>
      <Section title="Trust cards">
        <div className="d-grid">
          <TrustCard app={apps[4]!} now={NOW} placement={{ node: 'home-hub' }} />
          <TrustCard app={apps[6]!} now={NOW} placement={{ node: null, reasons: apps[6]!.why }} />
          <TrustCard app={apps[7]!} now={NOW} />
        </div>
      </Section>
      <Section title="Table and empty state">
        <div className="d-grid">
          <Card>
            <Table caption="Sortable" rowKey={(r) => r.n} initialSort={{ key: 'n', dir: 'asc' }} columns={[{ key: 'n', header: 'Name', sortValue: (r) => r.n }, { key: 'v', header: 'Value', align: 'end', sortValue: (r) => r.v }]} rows={[{ n: 'beta', v: 2 }, { n: 'alpha', v: 3 }, { n: 'gamma', v: 1 }]} />
          </Card>
          <Card>
            <EmptyState icon="backups" title="No backups yet" command="onemind backup now" action={<Button variant="primary">Set up backups</Button>}>
              Nothing on this box is protected. Add a USB disk, another box or an S3 bucket.
            </EmptyState>
          </Card>
        </div>
      </Section>
      <Section title="Dialog and toast">
        <div className="d-row">
          <Button onClick={() => setOpen(true)}>Open dialog</Button>
          <Button onClick={() => toast.show({ tone: 'ok', title: 'Saved', body: 'This goes away by itself.' })}>Success toast</Button>
          <Button onClick={() => toast.show({ tone: 'bad', title: 'Install failed', body: 'Errors stay until you close them.' })}>Error toast</Button>
        </div>
        <Dialog open={open} onClose={() => setOpen(false)} title="A dialog" description="Focus is trapped; Escape closes it." actions={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" onClick={() => setOpen(false)}>OK</Button></>} />
      </Section>
    </>
  );
}

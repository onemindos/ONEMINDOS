// SPDX-License-Identifier: Apache-2.0
// Updates (IA §2.8): booted slot, what is waiting, policy, history including rollbacks.
import { Button, Card, PageHeader, StatusPill, Table, formatAgo, secondsSince } from '../../../src';
import { Section } from '../bits';
import { NOW, apps, updates } from '../fixtures';

export function Updates() {
  const os = updates.os;
  return (
    <>
      <PageHeader title="Updates" lede="Security updates install automatically in your maintenance window if you allow it. Everything else waits for you. Every OS update can roll itself back." />
      <div className="d-grid-2">
        <Card
          title={`OneMind OS ${os.available} is ready`}
          subtitle="Security channel · fixes 2 CVEs in openssl and the Linux kernel"
          variant="attention"
          aside={<StatusPill tone="warn" label="Waiting for approval" />}
          footer={
            <div className="d-row">
              <Button variant="primary" icon="check">Approve for tonight 03:00</Button>
              <Button>Postpone 7 days</Button>
              <a href="#/updates" className="om-hint">Release notes</a>
            </div>
          }
        >
          <ul className="om-perm-list">
            <li>Takes a backup snapshot first.</li>
            <li>Installs into slot {os.other} while slot {os.booted} keeps running.</li>
            <li>Reboots into {os.other}; keeps it only if the cluster, the bus and your apps pass their health checks within 5 minutes. Otherwise it boots back into {os.booted} by itself.</li>
          </ul>
        </Card>
        <Card title="This box" subtitle="home-hub">
          <dl className="d-kv">
            <dt>Running</dt>
            <dd>OneMind OS {os.version} · slot {os.booted}</dd>
            <dt>Fallback</dt>
            <dd>OneMind OS {os.otherVersion} · slot {os.other}</dd>
            <dt>Channel</dt>
            <dd>{os.channel} (auto-install allowed)</dd>
            <dt>Window</dt>
            <dd>{os.window}</dd>
            <dt>Other nodes</dt>
            <dd>Update after this one passes (canary first)</dd>
          </dl>
        </Card>
      </div>
      <Section title="App updates">
        <Table
          caption="App updates"
          hideCaption
          rowKey={(r) => r.id}
          columns={[
            { key: 'name', header: 'App', render: (r) => <strong>{r.name}</strong> },
            { key: 'v', header: 'Version', render: (r) => (r.updateAvailable ? `${r.version} → ${r.updateAvailable}` : r.version) },
            { key: 'scan', header: 'Scan', secondary: true, render: (r) => (r.scan ? `passed ${formatAgo(secondsSince(r.scan.scanned_at, NOW))}` : '—') },
            { key: 's', header: 'State', render: (r) => (r.updateAvailable ? <StatusPill tone="warn" label="Waiting for approval" /> : <StatusPill tone="ok" label="Up to date" />) },
          ]}
          rows={apps.filter((a) => a.installed)}
        />
      </Section>
      <Section title="History">
        <Table
          caption="Update history"
          hideCaption
          rowKey={(r) => r.at + r.what}
          columns={[
            { key: 'at', header: 'When', render: (r) => formatAgo(secondsSince(r.at, NOW)) },
            { key: 'what', header: 'Update' },
            { key: 'node', header: 'Node', secondary: true },
            { key: 'label', header: 'Result', render: (r) => <StatusPill tone={r.result} label={r.label} /> },
          ]}
          rows={updates.history}
        />
      </Section>
    </>
  );
}

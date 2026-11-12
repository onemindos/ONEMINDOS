// SPDX-License-Identifier: Apache-2.0
// Backups (IA §2.7): last run, last VERIFIED restore, destinations, snapshots, keys.
import { useState } from 'react';
import { Button, Card, Dialog, Icon, PageHeader, StatusPill, Table, formatAgo, secondsSince, useToast } from '../../../src';
import { Section, Stat } from '../bits';
import { NOW, backup } from '../fixtures';

const TONE = { ok: 'ok', warn: 'warn' } as const;

export function Backups() {
  const toast = useToast();
  const [restore, setRestore] = useState<string>();
  return (
    <>
      <PageHeader
        title="Backups"
        lede={backup.schedule}
        actions={
          <>
            <Button icon="backups" onClick={() => toast.show({ tone: 'ok', title: 'Backup started', body: 'It runs in the background; Activity shows the result.' })}>
              Back up now
            </Button>
            <Button variant="primary" onClick={() => setRestore('latest')}>Restore…</Button>
          </>
        }
      />
      <div className="d-stats">
        <Stat label="Last backup" value={formatAgo(secondsSince(backup.lastRun, NOW))} detail="2 of 3 destinations current" tone="warn" />
        <Stat label="Last verified restore" value={formatAgo(secondsSince(backup.lastVerifiedRestore, NOW))} detail="Verified" tone="ok" />
        <Stat label="Protected" value="6 volumes" detail="+ cluster state" />
        <Stat label="Recovery keys" value="2 of 3" detail="Offsite key missing" tone="warn" />
      </div>
      <div className="d-banner om-tone-info">
        <Icon name="info" />
        <span>
          Every week a copy is restored to a scratch space and each app's health checks run against it. Only then is it marked <strong>verified</strong>. A backup you have never restored is a hope, not a backup.
        </span>
      </div>
      <Section title="Destinations">
        <Table
          caption="Backup destinations"
          hideCaption
          rowKey={(r) => r.id}
          columns={[
            { key: 'name', header: 'Destination', render: (r) => <><strong>{r.name}</strong><br /><span className="om-hint">{r.kind}</span></> },
            { key: 'size', header: 'Used', secondary: true },
            { key: 'last', header: 'Last success', render: (r) => formatAgo(secondsSince(r.last, NOW)) },
            { key: 'state', header: 'State', render: (r) => <StatusPill tone={TONE[r.state]} label={r.state === 'ok' ? 'Up to date' : 'Behind by 1 day'} /> },
          ]}
          rows={backup.destinations}
        />
      </Section>
      <div className="d-grid-2">
        <Section title="Snapshots">
          <Table
            caption="Snapshots"
            hideCaption
            rowKey={(r) => r.id}
            columns={[
              { key: 'at', header: 'Taken', render: (r) => formatAgo(secondsSince(r.at, NOW)) },
              { key: 'id', header: 'ID', secondary: true, render: (r) => <code>{r.id}</code> },
              { key: 'size', header: 'Size' },
              { key: 'v', header: 'Restore test', render: (r) => (r.verified ? <StatusPill tone="ok" label="Verified" /> : <StatusPill tone="neutral" label="Not tested yet" />) },
              { key: 'x', header: 'Actions', align: 'end', render: (r) => <Button size="sm" variant="ghost" onClick={() => setRestore(r.id)}>Restore…</Button> },
            ]}
            rows={backup.snapshots}
          />
        </Section>
        <Section title="Encryption keys">
          <Card>
            <ul className="d-list">
              {backup.keys.map((k) => (
                <li key={k.name}>
                  <Icon name="lock" />
                  <span className="d-list-main">
                    <strong>{k.name}</strong>
                    <br />
                    <span className="om-hint">{k.where}</span>
                  </span>
                  <StatusPill tone={TONE[k.state]} label={k.state === 'ok' ? 'Ready' : 'Set up'} />
                </li>
              ))}
            </ul>
          </Card>
        </Section>
      </div>
      <Dialog
        open={restore !== undefined}
        onClose={() => setRestore(undefined)}
        role="alertdialog"
        size="lg"
        title="Restore from a snapshot"
        description={`Snapshot ${restore === 'latest' ? backup.snapshots[0]!.id : restore}. Choose what to restore. Current data is snapshotted first, so a restore can itself be undone.`}
        actions={
          <>
            <Button onClick={() => setRestore(undefined)}>Cancel</Button>
            <Button
              variant="primary"
              onClick={() => {
                setRestore(undefined);
                toast.show({ tone: 'info', title: 'Restore requested', body: 'Approve it in Approvals to start.' });
              }}
            >
              Request restore
            </Button>
          </>
        }
      >
        <fieldset className="d-stack" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="om-subhead">What to restore</legend>
          <label className="d-row"><input type="radio" name="scope" defaultChecked /> One app: Home Assistant</label>
          <label className="d-row"><input type="radio" name="scope" /> One folder or file</label>
          <label className="d-row"><input type="radio" name="scope" /> The whole box (all apps and settings)</label>
        </fieldset>
      </Dialog>
    </>
  );
}

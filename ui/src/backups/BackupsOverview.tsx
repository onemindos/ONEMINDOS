// SPDX-License-Identifier: Apache-2.0
// Backups overview (IA §2.7, contract §12.12): health, the verified-restore badge per app,
// destinations, recent runs. Every button files a request; the owner approves it in Approvals
// (or, for their own request, at once). Nothing here changes anything by itself.
import { useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { Table } from '../components/Table';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { DestinationForm, type DestinationRequest } from './DestinationForm';
import { HEALTH, KIND_LABEL, REASON, RUN, badgeView, destinationWhere, formatBytes, overviewNotice, unitLabel } from './logic';
import './backups.css';
import type { BackupBadge, BackupRun, BackupsStatus, Load } from './types';

export function BackupBadgePill({ badge, now }: { badge?: BackupBadge; now: number }) {
  const v = badgeView(badge, now);
  return <StatusPill tone={v.tone} label={v.label} detail={v.detail} />;
}

export interface BackupsOverviewProps {
  status: Load<BackupsStatus>;
  runs: BackupRun[];
  now: number;
  /** The viewer may file owner-only requests (destinations, restore, kit). */
  isOwner: boolean;
  onBackupNow: () => void;
  onVerifyNow: () => void;
  onAddDestination: (req: DestinationRequest) => void;
  onRemoveDestination: (id: string) => void;
  onOpenKit: () => void;
  onOpenRewind: (appId?: string) => void;
  busy?: boolean;
}

export function BackupsOverview(p: BackupsOverviewProps) {
  const [adding, setAdding] = useState(false);
  if (p.status.status === 'loading') {
    return <p className="om-hint" role="status">Loading backups…</p>;
  }
  if (p.status.status === 'error') {
    return (
      <EmptyState icon="alert" title="Backups could not be read">
        {p.status.code}: {p.status.message}
      </EmptyState>
    );
  }
  const s = p.status.data;
  const stale = p.status.stale === true;
  const health = HEALTH[s.health];
  const notice = overviewNotice(s);
  const apps = Object.entries(s.badges.apps).sort(([a], [b]) => a.localeCompare(b));
  const canRequest = !stale && s.agent === 'ok';
  return (
    <section className="omb-overview" aria-labelledby="omb-title">
      <header className="omb-head">
        <div>
          <h1 id="omb-title" className="omb-title">Backups</h1>
          <p className="om-hint">
            <StatusPill tone={health.tone} label={health.label} detail={s.reason ?? undefined} />
          </p>
        </div>
        <div className="omb-actions">
          <Button icon="backups" onClick={p.onBackupNow} disabled={!canRequest || s.destinations.length === 0} busy={p.busy}>
            Back up now
          </Button>
          <Button onClick={p.onVerifyNow} disabled={!canRequest || !s.last_success_at}>
            Test a restore now
          </Button>
          <Button variant="primary" onClick={() => p.onOpenRewind()} disabled={!s.last_success_at}>
            Restore…
          </Button>
        </div>
      </header>

      {stale && (
        <div className="omb-banner om-tone-warn" role="status">
          <Icon name="clock" /> This is the last known state, not live. Requests are paused until the hub answers.
        </div>
      )}
      {notice && (
        <div className={`omb-banner om-tone-${notice.tone}`} role="note">
          <Icon name={notice.tone === 'bad' ? 'alert' : 'info'} />
          <span>{notice.text}</span>
          {s.kit.state !== 'confirmed' && s.destinations.length > 0 && p.isOwner && (
            <Button size="sm" variant="primary" icon="lock" onClick={p.onOpenKit}>
              Save the emergency kit
            </Button>
          )}
        </div>
      )}

      <dl className="omb-stats">
        <div>
          <dt>Last backup</dt>
          <dd>{s.last_success_at ? formatAgo(secondsSince(s.last_success_at, p.now)) : 'never'}</dd>
        </div>
        <div>
          <dt>Last tested restore</dt>
          <dd>{s.last_verified_restore_at ? formatAgo(secondsSince(s.last_verified_restore_at, p.now)) : 'never'}</dd>
        </div>
        <div>
          <dt>Next backup</dt>
          <dd>{s.next_run_at ? formatIn(s.next_run_at, p.now) : 'not scheduled'}</dd>
        </div>
        <div>
          <dt>Copies</dt>
          <dd>{s.copies}</dd>
        </div>
      </dl>

      <Card title="Is it really safe?" level={2} subtitle="A backup turns green only after the box has restored it into a scratch space and read every file back.">
        <ul className="omb-badges">
          <li>
            <span className="omb-badge-name">Whole box</span>
            <BackupBadgePill badge={s.badges.box} now={p.now} />
          </li>
          <li>
            <span className="omb-badge-name">{unitLabel('system')}</span>
            <BackupBadgePill badge={s.badges.system} now={p.now} />
          </li>
          {apps.map(([id, b]) => (
            <li key={id}>
              <span className="omb-badge-name">
                {id}
                {s.crash_consistent_apps.includes(id) && <span className="om-hint"> · copied while running (no backup hooks)</span>}
              </span>
              <BackupBadgePill badge={b} now={p.now} />
              <Button size="sm" variant="ghost" onClick={() => p.onOpenRewind(id)} aria-label={`Browse or restore ${id}`}>
                Browse
              </Button>
            </li>
          ))}
        </ul>
        <p className="om-hint">
          Verified: a restore test passed in the last 8 days and the last backup worked within 2 hours.
          Backed up, not verified: backups work, but no restore test has passed recently.
        </p>
      </Card>

      <Card
        title="Where backups go"
        level={2}
        aside={p.isOwner ? <Button size="sm" icon="plus" onClick={() => setAdding(true)} disabled={stale}>Add destination</Button> : undefined}
      >
        <Table
          caption="Backup destinations"
          hideCaption
          rowKey={(d) => d.id}
          rows={s.destinations}
          empty={<EmptyState icon="backups" title="No destination yet">A USB disk, another OneMind box or an S3 bucket.</EmptyState>}
          columns={[
            { key: 'label', header: 'Destination', render: (d) => <><strong>{d.label}</strong>{d.primary && <span className="om-hint"> · hourly</span>}<br /><span className="om-hint">{KIND_LABEL[d.kind]}</span></> },
            { key: 'where', header: 'Where', secondary: true, render: (d) => <code>{destinationWhere(d)}</code> },
            { key: 'ro', header: 'Protection', render: (d) => (d.append_only ? <StatusPill tone="ok" label="Append-only" detail="this box cannot delete it" /> : <StatusPill tone="neutral" label="Normal" />) },
            {
              key: 'x', header: 'Actions', align: 'end',
              render: (d) => (p.isOwner ? <Button size="sm" variant="ghost" onClick={() => p.onRemoveDestination(d.id)} disabled={stale}>Remove…</Button> : null),
            },
          ]}
        />
      </Card>

      <Card title="Recent runs" level={2}>
        <Table
          caption="Recent backup runs"
          hideCaption
          rowKey={(r) => r.id}
          rows={p.runs.slice(0, 10)}
          empty={<p className="om-hint">No backup has run yet.</p>}
          columns={[
            { key: 'when', header: 'When', render: (r) => formatAgo(secondsSince(r.started_at, p.now)) },
            { key: 'why', header: 'Why', render: (r) => REASON[r.reason] ?? r.reason },
            { key: 'state', header: 'Result', render: (r) => <StatusPill tone={RUN[r.state].tone} label={RUN[r.state].label} pulse={r.state === 'running'} /> },
            {
              key: 'units', header: 'Details', secondary: true,
              render: (r) => {
                const failed = r.units.filter((u) => u.state !== 'succeeded');
                return failed.length
                  ? failed.map((u) => `${unitLabel(u.unit)}: ${u.error ?? u.state}`).join('; ')
                  : `${r.units.length} parts · ${formatBytes(r.bytes_done)} new`;
              },
            },
          ]}
        />
      </Card>

      <DestinationForm open={adding} onClose={() => setAdding(false)} onSubmit={(req) => { setAdding(false); p.onAddDestination(req); }} />
    </section>
  );
}

// SPDX-License-Identifier: Apache-2.0
// Settings sections that keep the box healthy: Backups, Updates, Notifications, Automation.
import { useState } from 'react';
import { formatAgo, formatDay, formatIn, secondsSince } from '../lib/time';
import { BRAND } from '../components/BrandMark';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { StatusPill } from '../components/StatusPill';
import type { Tone } from '../tokens/tokens';
import { byDeployClass, formatGb, inQuietHours, minutesOf, restoreBadge } from './logic';
import { Async, CallHint, Empty, Fact, Group, Row, Rows, SectionHead, SetIcon, Switch } from './primitives';
import type { SectionProps } from './SectionsAccess';
import { CATEGORY_LABEL, DEPLOY_CLASS } from './taxonomy';
import type { AutomationRule, BackupsData, NotificationsData, Severity, UpdatesData } from './types';

const ago = (iso: string | null, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : 'never');

/* ---------- Backups ---------- */
const DEST_STATE: Record<'current' | 'behind' | 'failing', { tone: Tone; label: string }> = {
  current: { tone: 'ok', label: 'Current' },
  behind: { tone: 'warn', label: 'Behind' },
  failing: { tone: 'bad', label: 'Failing' },
};
type Scope = 'app' | 'folder' | 'box';

export function BackupsSection({ data, now, onIntent, onRetry }: SectionProps<BackupsData>) {
  const [restore, setRestore] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>('app');
  return (
    <>
      <SectionHead icon="backups" title="Backups" lede="Where copies go, how often, and when a restore was last proven to work." />
      <Async value={data} label="backups" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => {
          const badge = restoreBadge(d.lastVerifiedRestore, now);
          const latest = d.destinations.map((x) => x.last_success_at).filter(Boolean).sort().pop() ?? null;
          return (
            <>
              <div className={`om-set-hero om-tone-${badge.tone}`}>
                <span className="om-set-hero-icon" aria-hidden="true">
                  <SetIcon name={badge.tone === 'ok' ? 'approvals' : 'alert'} size={28} />
                </span>
                <div>
                  <p className="om-set-hero-title">{badge.label}</p>
                  <p className="om-set-hero-text">
                    {badge.detail}
                    {d.lastVerifiedRestore && ` The box restored ${d.lastVerifiedRestore.scope} from ${d.lastVerifiedRestore.snapshot} into a scratch area and checked it.`}
                  </p>
                </div>
                <Button size="sm" disabled={!live} onClick={() => onIntent({ type: 'backup.verify', params: {}, mode: 'request', title: 'Test a restore now', call: 'onemind backups verify' })}>
                  Test a restore now
                </Button>
              </div>
              <div className="om-set-facts">
                <Fact label="Last backup" value={ago(latest, now)} />
                <Fact label="Destinations current" value={`${d.destinations.filter((x) => x.state === 'current').length} of ${d.destinations.length}`} />
                <Fact label="Emergency kit" value={d.emergencyKit.saved ? `${d.emergencyKit.keys} of ${d.emergencyKit.of} keys saved` : 'Not saved'} pill={
                    !d.emergencyKit.saved ? (
                      <StatusPill tone="bad" label="Save it now" />
                    ) : d.emergencyKit.keys < d.emergencyKit.of ? (
                      <StatusPill tone="warn" label={`${d.emergencyKit.of - d.emergencyKit.keys} key${d.emergencyKit.of - d.emergencyKit.keys === 1 ? '' : 's'} missing`} />
                    ) : (
                      <StatusPill tone="ok" label="Complete" />
                    )
                  } />
              </div>
              <Group
                title="Destinations"
                description="Every copy is encrypted on this box before it leaves. Adding or changing a destination needs your passkey."
                aside={
                  <Button size="sm" icon="plus" disabled={!live} onClick={() => onIntent({ type: 'backup.destination.add', params: {}, mode: 'request', title: 'Add a backup destination', call: 'onemind backups destinations add' })}>
                    Add
                  </Button>
                }
              >
                {d.destinations.length === 0 ? (
                  <Empty icon="backups" title="No backups yet" command="onemind backups destinations add usb">
                    Plug in a USB disk or add another box or an S3 bucket. Until then, your data has one copy.
                  </Empty>
                ) : (
                  <Rows label="Destinations">
                    {d.destinations.map((x) => (
                      <Row
                        key={x.id}
                        icon={x.kind === 's3' ? 'globe' : x.kind === 'box' ? 'nodes' : 'disk'}
                        title={x.name}
                        description={`${x.kind === 's3' ? 'Object storage' : x.kind === 'box' ? 'Another OneMind' : 'USB disk'} · ${formatGb(x.used_gb)} · last copy ${ago(x.last_success_at, now)}`}
                        trailing={<StatusPill {...DEST_STATE[x.state]} />}
                      />
                    ))}
                  </Rows>
                )}
              </Group>
              <Group title="Schedule">
                <Rows label="Schedule">
                  <Row icon="clock" title={d.schedule.every === 'daily' ? `Every day at ${d.schedule.at}` : 'Every hour'} description={`Keeps ${d.schedule.keep}.`} trailing={<Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'backup.schedule.set', params: {}, mode: 'request', title: 'Change the backup schedule', call: 'PUT /v1/backups/schedule' })}>Change…</Button>} />
                </Rows>
              </Group>
              <Group title="Recent snapshots">
                {d.snapshots.length === 0 ? (
                  <Empty icon="clock" title="No snapshots yet">The first one is made at the next scheduled time.</Empty>
                ) : (
                  <Rows label="Snapshots">
                    {d.snapshots.map((s) => (
                      <Row
                        key={s.id}
                        icon="backups"
                        title={`${formatDay(s.at)} · ${ago(s.at, now)}`}
                        description={`${s.id} · ${formatGb(s.size_gb)}`}
                        trailing={
                          <span className="om-set-actions">
                            <StatusPill tone={s.verified === 'ok' ? 'ok' : s.verified === 'failed' ? 'bad' : 'neutral'} label={s.verified === 'ok' ? 'Restore tested' : s.verified === 'failed' ? 'Test failed' : 'Not tested'} dot={s.verified !== 'untested'} />
                            <Button size="sm" variant="ghost" disabled={!live} onClick={() => setRestore(s.id)}>
                              Restore…
                            </Button>
                          </span>
                        }
                      />
                    ))}
                  </Rows>
                )}
              </Group>
            </>
          );
        }}
      </Async>
      <Dialog
        open={restore !== null}
        onClose={() => setRestore(null)}
        role="alertdialog"
        title="Request a restore"
        description="Your current data is snapshotted first, so a restore can itself be undone. The request waits in Approvals and needs your passkey."
        actions={
          <>
            <Button onClick={() => setRestore(null)}>Cancel</Button>
            <Button
              variant="primary"
              onClick={() => {
                onIntent({ type: 'backup.restore', params: { snapshot: restore, scope }, mode: 'request', title: `Restore ${scope === 'box' ? 'the whole box' : scope === 'app' ? 'one app' : 'a folder'} from ${restore}`, call: 'POST /v1/restores' });
                setRestore(null);
              }}
            >
              Request restore
            </Button>
          </>
        }
      >
        <fieldset className="om-set-choices">
          <legend>What to restore from {restore}</legend>
          {(
            [
              ['app', 'One app', 'Its data volumes, as they were.'],
              ['folder', 'A folder', 'Pick files from an app or a shared folder.'],
              ['box', 'The whole box', 'Every app and the OneMind settings. Apps restart.'],
            ] as Array<[Scope, string, string]>
          ).map(([v, t, h]) => (
            <label key={v} className="om-set-choice">
              <input type="radio" name="restore-scope" value={v} checked={scope === v} onChange={() => setScope(v)} />
              <span>
                <strong>{t}</strong>
                <span className="om-set-meta">{h}</span>
              </span>
            </label>
          ))}
        </fieldset>
      </Dialog>
      <CallHint calls={['GET /v1/backups', 'onemind backups now', 'onemind backups verify', 'POST /v1/restores   (action backup.restore; always needs the owner passkey)']} />
    </>
  );
}

/* ---------- Updates ---------- */
const CHANNELS: Array<[UpdatesData['channel'], string, string]> = [
  ['security', 'Security only', 'Only fixes for security problems.'],
  ['stable', 'Stable', 'Tested releases, about once a month.'],
  ['beta', 'Beta', 'Earlier releases for people who help test.'],
];
const HIST: Record<'kept' | 'rolled-back' | 'failed', { tone: Tone; label: string }> = {
  kept: { tone: 'ok', label: 'Kept' },
  'rolled-back': { tone: 'warn', label: 'Rolled back' },
  failed: { tone: 'bad', label: 'Failed' },
};

export function UpdatesSection({ data, now, onIntent, onRetry }: SectionProps<UpdatesData>) {
  return (
    <>
      <SectionHead icon="updates" title="Updates" lede="The system updates into a second slot and keeps the new version only if every health check passes. Otherwise it boots the old one again." />
      <Async value={data} label="update status" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => (
          <>
            <div className="om-set-slots" role="group" aria-label="System slots">
              {(['A', 'B'] as const).map((slot) => {
                const booted = d.slot === slot;
                const version = booted ? d.version : d.fallback?.slot === slot ? d.fallback.version : null;
                return (
                  <div key={slot} className="om-set-slot" data-booted={booted}>
                    <span className="om-set-slot-name">Slot {slot}</span>
                    <span className="om-set-slot-ver">{version ?? 'Empty'}</span>
                    <StatusPill tone={booted ? 'ok' : 'neutral'} label={booted ? 'Running' : version ? 'Fallback' : 'Unused'} dot={booted} />
                  </div>
                );
              })}
            </div>
            {d.available ? (
              <Group
                title={`${BRAND.name} ${d.available.version} is ready`}
                description={`${d.available.channel} channel · ${d.available.size_mb} MB · fixes ${d.available.cvesFixed} known vulnerabilit${d.available.cvesFixed === 1 ? 'y' : 'ies'}`}
                aside={
                  <Button variant="primary" size="sm" disabled={!live} onClick={() => onIntent({ type: 'os.update', params: { to: d.available!.version, when: 'window' }, mode: 'request', title: `Update to ${d.available!.version} in the window`, call: `onemind os update --to ${d.available!.version} --in-window` })}>
                    Request for {d.window.start}
                  </Button>
                }
              >
                <details className="om-details" open>
                  <summary>Release notes</summary>
                  <ul className="om-set-notes">
                    {d.available.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                </details>
              </Group>
            ) : (
              <p className="om-note om-tone-ok">You are on the latest {d.channel} release.</p>
            )}
            <Group title="Policy">
              <fieldset className="om-set-choices">
                <legend className="om-visually-hidden">Update channel</legend>
                {CHANNELS.map(([v, t, h]) => (
                  <label key={v} className="om-set-choice">
                    <input
                      type="radio"
                      name="channel"
                      value={v}
                      checked={d.channel === v}
                      disabled={!live}
                      onChange={() => onIntent({ type: 'os.update.settings', params: { channel: v }, mode: 'request', title: `Switch to the ${t} channel`, call: `PUT /v1/os/settings {"channel":"${v}"}` })}
                    />
                    <span>
                      <strong>{t}</strong>
                      <span className="om-set-meta">{h}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
              <Rows label="Maintenance window">
                <Row icon="clock" title={`Maintenance window ${d.window.start}–${d.window.end}`} description="Approved updates install then. Nodes update one at a time, the hub last." trailing={<Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'os.update.settings', params: { window: d.window }, mode: 'request', title: 'Change the maintenance window', call: 'PUT /v1/os/settings' })}>Change…</Button>} />
              </Rows>
            </Group>
            <Group title={`App updates (${d.apps.length})`} description="Grouped by how far OneMind vouches for each app. Each update snapshots the app first and reverts if it is unhealthy." aside={d.apps.length > 1 && <Button size="sm" disabled={!live} onClick={() => onIntent({ type: 'app.update.batch', params: { apps: d.apps.map((a) => a.app_id) }, mode: 'request', title: `Update ${d.apps.length} apps`, call: 'onemind apps update --all' })}>Request all</Button>}>
              {d.apps.length === 0 ? (
                <Empty icon="check" title="Every app is up to date" command="onemind apps outdated" />
              ) : (
                byDeployClass(d.apps).map((g) => (
                  <div key={g.cls} className="om-set-subgroup">
                    <h4 className="om-set-subhead">
                      <StatusPill tone={DEPLOY_CLASS[g.cls].tone} label={DEPLOY_CLASS[g.cls].label} dot={false} /> <span className="om-set-meta">{DEPLOY_CLASS[g.cls].sentence}</span>
                    </h4>
                    <Rows label={`${DEPLOY_CLASS[g.cls].label} updates`}>
                      {g.items.map((a) => (
                        <Row
                          key={a.app_id}
                          icon="apps"
                          title={`${a.name} ${a.from} → ${a.to}`}
                          description={CATEGORY_LABEL[a.category]}
                          meta={a.notes.join(' · ')}
                          trailing={
                            <Button size="sm" disabled={!live} onClick={() => onIntent({ type: 'app.update', params: { app_id: a.app_id, to: a.to }, mode: 'request', title: `Update ${a.name} to ${a.to}`, call: `onemind apps update ${a.app_id}` })}>
                              Request
                            </Button>
                          }
                        />
                      ))}
                    </Rows>
                  </div>
                ))
              )}
            </Group>
            <Group title="History">
              {d.history.length === 0 ? (
                <Empty icon="clock" title="No updates yet">The first update will be listed here with its result.</Empty>
              ) : (
                <Rows label="Update history">
                  {d.history.map((h) => (
                    <Row
                      key={h.at}
                      icon="updates"
                      tone={h.result === 'kept' ? undefined : HIST[h.result].tone}
                      title={`${h.from} → ${h.to}`}
                      description={`${formatDay(h.at)} · approved by ${h.by}`}
                      meta={h.check ? `Health check that failed: ${h.check}. The box went back to ${h.from} by itself.` : undefined}
                      trailing={<StatusPill {...HIST[h.result]} />}
                    />
                  ))}
                </Rows>
              )}
            </Group>
          </>
        )}
      </Async>
      <CallHint calls={['GET /v1/os/status', 'onemind os update --in-window', 'PUT /v1/os/settings   (an os.update.settings request)', 'onemind os rollback   (rescue console too)']} />
    </>
  );
}

/* ---------- Notifications ---------- */
const SEVERITY: Severity[] = ['info', 'warning', 'critical'];
const SEV_LABEL: Record<Severity, string> = { info: 'Everything', warning: 'Warnings and up', critical: 'Critical only' };
const CH_STATE: Record<'ok' | 'failing' | 'off', { tone: Tone; label: string }> = {
  ok: { tone: 'ok', label: 'Working' },
  failing: { tone: 'bad', label: 'Failing' },
  off: { tone: 'neutral', label: 'Off' },
};

export function NotificationsSection({ data, now, onIntent, onRetry }: SectionProps<NotificationsData>) {
  return (
    <>
      <SectionHead icon="bell" title="Notifications" lede="Where alerts reach you and when they stay quiet. A request that needs you always shows in the app." />
      <Async value={data} label="notification settings" now={now} onRetry={onRetry} rows={4}>
        {(d, live) => {
          const minute = new Date(now).getUTCHours() * 60 + new Date(now).getUTCMinutes();
          const quietNow = inQuietHours(d.quiet, minute);
          const validQuiet = Number.isFinite(minutesOf(d.quiet.start)) && Number.isFinite(minutesOf(d.quiet.end));
          return (
            <>
              <Group title="Channels" aside={<Button size="sm" icon="plus" disabled={!live} onClick={() => onIntent({ type: 'notify.route.add', params: {}, mode: 'request', title: 'Add a notification channel', call: 'POST /v1/notifications/channels' })}>Add</Button>}>
                {d.channels.length === 0 ? (
                  <Empty icon="bell" title="Only in the app" command="onemind notify routes add">
                    Add your phone so a backup failure or a waiting request reaches you away from the screen.
                  </Empty>
                ) : (
                  <Rows label="Channels">
                    {d.channels.map((c) => (
                      <Row
                        key={c.id}
                        icon="bell"
                        title={
                          <>
                            {c.label} <StatusPill {...CH_STATE[c.state]} />
                          </>
                        }
                        description={c.state === 'failing' ? `Last delivery ${ago(c.last_delivery_at, now)}. Check the channel, then send a test.` : `Last delivery ${ago(c.last_delivery_at, now)}`}
                        trailing={
                          <span className="om-set-actions">
                            <label className="om-set-select">
                              <span className="om-visually-hidden">What {c.label} receives</span>
                              <select
                                value={c.minSeverity}
                                disabled={!live || c.kind === 'in-app'}
                                onChange={(e) => onIntent({ type: 'notify.route.set', params: { id: c.id, min_severity: e.target.value }, mode: 'instant', title: `${c.label}: ${SEV_LABEL[e.target.value as Severity]}`, call: `PUT /v1/notifications/channels/${c.id}` })}
                              >
                                {SEVERITY.map((s) => (
                                  <option key={s} value={s}>
                                    {SEV_LABEL[s]}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {c.kind !== 'in-app' && (
                              <Button size="sm" variant="ghost" disabled={!live} onClick={() => onIntent({ type: 'notify.test', params: { id: c.id }, mode: 'instant', title: `Test sent to ${c.label}`, call: `POST /v1/notifications/channels/${c.id}/test` })}>
                                Test
                              </Button>
                            )}
                          </span>
                        }
                      />
                    ))}
                  </Rows>
                )}
              </Group>
              <Group title="Quiet hours" description="Times are the box's time zone." aside={<StatusPill tone={quietNow ? 'info' : 'neutral'} label={quietNow ? 'Quiet now' : 'Not quiet now'} dot={quietNow} />}>
                <Rows label="Quiet hours">
                  <Row
                    icon="clock"
                    title={validQuiet ? `From ${d.quiet.start} to ${d.quiet.end}` : 'Quiet hours are not set correctly'}
                    description="Pushes wait until the morning; they still appear in the app."
                    trailing={<Switch checked={d.quiet.enabled} label="Quiet hours" disabled={!live} onToggle={() => onIntent({ type: 'notify.quiet.set', params: { enabled: !d.quiet.enabled }, mode: 'instant', title: d.quiet.enabled ? 'Quiet hours off' : 'Quiet hours on', call: 'PUT /v1/notifications/preferences' })} />}
                  />
                  <Row
                    icon="alert"
                    title="Critical alerts break through"
                    description="A failing disk or a broken audit chain wakes you even during quiet hours."
                    trailing={<Switch checked={d.quiet.allowCritical} label="Critical alerts break through" disabled={!live} onToggle={() => onIntent({ type: 'notify.quiet.set', params: { allow_critical: !d.quiet.allowCritical }, mode: 'instant', title: 'Changed critical alerts', call: 'PUT /v1/notifications/preferences' })} />}
                  />
                </Rows>
              </Group>
            </>
          );
        }}
      </Async>
      <CallHint calls={['GET /v1/notifications/channels', 'POST /v1/notifications/channels/{id}/test', 'PUT /v1/notifications/preferences']} />
    </>
  );
}

/* ---------- Automation ---------- */
const TRIGGER: Record<AutomationRule['trigger']['kind'], string> = { schedule: 'On a schedule', event: 'When an event happens', webhook: 'When a webhook is called' };

export function AutomationSection({ data, now, onIntent, onRetry }: SectionProps<AutomationRule[]>) {
  return (
    <>
      <SectionHead
        icon="flow"
        title="Automation"
        lede="Rules that create requests for you: on a schedule, on an event, or from a webhook. A rule never changes anything by itself."
        aside={<StatusPill tone="info" label="Preview" dot={false} />}
      />
      <Async
        value={data}
        label="automation rules"
        now={now}
        onRetry={onRetry}
        isEmpty={(d) => d.length === 0}
        empty={
          <Empty icon="info" title="No rules yet" command="onemind automations list">
            Rules arrive with the automation engine (AUTO-4). Each will show what it would request in a dry run before you turn it on.
          </Empty>
        }
      >
        {(d, live) => (
          <Group title={`Rules (${d.length})`} description="“Standing approval” means you approved this rule once with limits; each run still appears in Activity.">
            <Rows label="Rules">
              {d.map((r) => (
                <Row
                  key={r.id}
                  icon="flow"
                  title={
                    <>
                      {r.name} <StatusPill tone={r.policy === 'standing' ? 'info' : 'neutral'} label={r.policy === 'standing' ? 'Standing approval' : 'Asks each time'} dot={false} />
                    </>
                  }
                  description={`${TRIGGER[r.trigger.kind]}: ${r.trigger.detail} → requests ${r.creates}`}
                  meta={`Last run ${ago(r.last_run_at, now)}${r.next_run_at ? ` · next ${formatIn(r.next_run_at, now)}` : ''}`}
                  trailing={<Switch checked={r.state === 'on'} label={`Rule ${r.name}`} disabled={!live} onToggle={() => onIntent({ type: 'automation.set', params: { id: r.id, state: r.state === 'on' ? 'paused' : 'on' }, mode: r.state === 'on' ? 'instant' : 'request', title: r.state === 'on' ? `Paused ${r.name}` : `Turn on ${r.name}`, call: `PUT /v1/automation/rules/${r.id}` })} />}
                />
              ))}
            </Rows>
          </Group>
        )}
      </Async>
      <CallHint calls={['GET /v1/automation/rules', 'POST /v1/automation/rules/{id}/dry-run', 'PUT /v1/automation/rules/{id}   (pausing is instant; turning on is a request)']} />
    </>
  );
}

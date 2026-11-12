// SPDX-License-Identifier: Apache-2.0
// Installed apps manager (PU-07, PU-08, PD-03, PD-06, PD-07, APP-P1-P3): list with honest state,
// and a per-app page with open, restart, stop/start, update with release notes, settings, logs,
// history, credentials and first-run steps, and uninstall that keeps data by default.
// Every change is a request (P1); the dialogs show the request and its API equivalent (P4).
import { useId, useState, type ReactNode } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Dialog } from '../components/Dialog';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { freshness } from '../lib/freshness';
import { formatAgo, formatDay, secondsSince } from '../lib/time';
import type { Tone } from '../tokens/tokens';
import { ReleaseNotes } from './AppDetail';
import { AppTile, ClassPills, LoadGate, RequestDetails, Tabs } from './bits';
import { CategoryIcon } from './CategoryIcon';
import { CATEGORY_BY_SLUG } from './taxonomy';
import { JobProgress } from './Jobs';
import { LogViewer } from './LogViewer';
import { apiEquivalent, buildRequest, cliEquivalent, hasUpdate, isJobActive, isProposedAction } from './logic';
import type { InstalledApp, LoadState, LogLine, SettingField, StoreActionRequest, StoreActionType, StoreJob } from './types';

// ---------------------------------------------------------------- honest state (P2)

const RUN_VIEW: Record<InstalledApp['state'], { tone: Tone; label: string }> = {
  running: { tone: 'ok', label: 'Running' },
  installed: { tone: 'info', label: 'Installed' },
  starting: { tone: 'info', label: 'Starting' },
  stopped: { tone: 'neutral', label: 'Stopped' },
  unhealthy: { tone: 'bad', label: 'Unhealthy' },
  updating: { tone: 'info', label: 'Updating' },
  unknown: { tone: 'neutral', label: 'Unknown' },
};

/** A state is live only while the hub's health check is fresh; otherwise say what was last known. */
export function appStateView(inst: Pick<InstalledApp, 'state' | 'checked_at'>, now: number): { tone: Tone; label: string; detail?: string; live: boolean } {
  const age = secondsSince(inst.checked_at, now);
  const f = freshness(age);
  const v = RUN_VIEW[inst.state];
  if (f === 'live') return { ...v, live: true };
  if (f === 'stale') return { tone: 'warn', label: 'Stale', detail: `last known ${v.label.toLowerCase()} ${formatAgo(age)}`, live: false };
  return { tone: 'neutral', label: 'Unknown', detail: f === 'unknown' ? 'never checked' : `last known ${v.label.toLowerCase()} ${formatAgo(age)}`, live: false };
}

// ---------------------------------------------------------------- confirm a request

function RequestDialog({
  open,
  onClose,
  title,
  req,
  role = 'dialog',
  children,
  confirmLabel,
  confirmDisabled,
  danger,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  req: StoreActionRequest;
  role?: 'dialog' | 'alertdialog';
  children: ReactNode;
  confirmLabel: string;
  confirmDisabled?: boolean;
  danger?: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      role={role}
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant={danger ? 'danger' : 'primary'} disabled={confirmDisabled} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="om-store-review">
        {children}
        <p className="om-hint">This creates a request. Nothing changes until an owner approves it in Approvals.</p>
        <RequestDetails api={apiEquivalent(req)} cli={cliEquivalent(req)} proposed={isProposedAction(req.type)} />
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------- credentials (PD-07)

export function CredentialsCard({ inst, isOwner, onCopied }: { inst: InstalledApp; isOwner: boolean; onCopied?: (label: string) => void }) {
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState('');
  const creds = inst.credentials ?? [];
  if (creds.length === 0 && !(inst.first_run ?? []).length) return null;
  const copy = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(`${label} copied`);
      onCopied?.(label);
    } catch {
      setCopied('Copy is not allowed here. Reveal it and copy by hand.');
    }
  };
  return (
    <Card title="Sign in and first run" level={2} subtitle="Sealed on this box. Shown only to the owner, never to agents or in logs.">
      {creds.length > 0 &&
        (isOwner ? (
          <dl className="om-store-creds">
            {creds.map((c) => {
              const visible = !c.secret || shown[c.label];
              return (
                <div key={c.label}>
                  <dt>{c.label}</dt>
                  <dd>
                    <code className={cx(!visible && 'om-store-masked')} aria-label={visible ? undefined : `${c.label} hidden`}>
                      {visible ? c.value : '••••••••••••'}
                    </code>
                    {c.secret && (
                      <button
                        type="button"
                        className="om-icon-btn"
                        aria-pressed={!!shown[c.label]}
                        aria-label={`${shown[c.label] ? 'Hide' : 'Reveal'} ${c.label}`}
                        onClick={() => setShown((s) => ({ ...s, [c.label]: !s[c.label] }))}
                      >
                        <CategoryIcon name={shown[c.label] ? 'eyeOff' : 'eye'} size={18} />
                      </button>
                    )}
                    <button type="button" className="om-icon-btn" aria-label={`Copy ${c.label}`} onClick={() => void copy(c.label, c.value)}>
                      <CategoryIcon name="copy" size={18} />
                    </button>
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : (
          <p className="om-note om-tone-neutral">Only the owner can see this app's credentials.</p>
        ))}
      <p className="om-visually-hidden" role="status">
        {copied}
      </p>
      {(inst.first_run ?? []).length > 0 && (
        <>
          <h3 className="om-subhead">First-run steps</h3>
          <ol className="om-store-firstrun">
            {inst.first_run!.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- settings (PD-09)

function SettingsForm({ inst, onRequest, disabled }: { inst: InstalledApp; onRequest: (r: StoreActionRequest) => void; disabled?: string }) {
  const fields = inst.settings ?? [];
  const [vals, setVals] = useState<Record<string, SettingField['value']>>(() => Object.fromEntries(fields.map((f) => [f.key, f.value])));
  const changed = fields.filter((f) => vals[f.key] !== f.value);
  const restarts = changed.some((f) => f.restarts);
  const base = useId();
  if (fields.length === 0)
    return (
      <EmptyState icon="settings" title="No settings to change" command={`onemind apps configure ${inst.app.id}`}>
        <p>{inst.app.name} does not publish a settings schema. Configure it inside the app.</p>
      </EmptyState>
    );
  return (
    <form
      className="om-store-form"
      onSubmit={(e) => {
        e.preventDefault();
        onRequest(buildRequest('app.configure', inst.app, { values: Object.fromEntries(changed.map((f) => [f.key, vals[f.key]])) }));
      }}
    >
      {fields.map((f) => {
        const id = `${base}-${f.key}`;
        const hint = f.hint || f.restarts ? `${id}-hint` : undefined;
        return (
          <div key={f.key} className={cx('om-store-field', f.kind === 'boolean' && 'om-store-field-row')}>
            {f.kind === 'boolean' ? (
              <input id={id} type="checkbox" checked={!!vals[f.key]} aria-describedby={hint} onChange={(e) => setVals((v) => ({ ...v, [f.key]: e.target.checked }))} />
            ) : null}
            <label htmlFor={id}>{f.label}</label>
            {f.kind === 'select' ? (
              <select id={id} value={String(vals[f.key])} aria-describedby={hint} onChange={(e) => setVals((v) => ({ ...v, [f.key]: e.target.value }))}>
                {(f.options ?? []).map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            ) : f.kind === 'boolean' ? null : (
              <input
                id={id}
                type={f.kind === 'number' ? 'number' : 'text'}
                value={String(vals[f.key])}
                aria-describedby={hint}
                onChange={(e) => setVals((v) => ({ ...v, [f.key]: f.kind === 'number' ? Number(e.target.value) : e.target.value }))}
              />
            )}
            {hint && (
              <span id={hint} className="om-store-field-hint">
                {f.hint}
                {f.restarts ? `${f.hint ? ' ' : ''}Changing it restarts the app.` : ''}
              </span>
            )}
          </div>
        );
      })}
      <div className="om-store-row">
        <Button type="submit" variant="primary" disabled={changed.length === 0 || !!disabled}>
          Request {changed.length || ''} {changed.length === 1 ? 'change' : 'changes'}
        </Button>
        <span className="om-hint">{disabled ?? (restarts ? 'The app restarts when this is applied.' : 'Saved as one request.')}</span>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- list

export interface InstalledListProps {
  apps: InstalledApp[];
  state: LoadState;
  now: number;
  jobs?: StoreJob[];
  manageHref: (id: string) => string;
  onOpen: (inst: InstalledApp) => void;
  onRequest: (req: StoreActionRequest) => void;
  /** 'updates' shows only apps with an update and the batched request (PU-08). */
  view?: 'all' | 'updates';
  onRetry?: () => void;
}

export function InstalledList({ apps, state, now, jobs = [], manageHref, onOpen, onRequest, view = 'all', onRetry }: InstalledListProps) {
  const updates = apps.filter((a) => hasUpdate(a.app.version, a.update));
  const shown = view === 'updates' ? updates : apps;
  const stale = state.kind === 'ready' && state.stale;
  const [batch, setBatch] = useState(false);
  const batchReq = buildRequest('app.update', { id: updates.map((u) => u.app.id).join(','), name: `${updates.length} apps` }, {
    apps: updates.map((u) => ({ app_id: u.app.id, to_version: u.update!.version })),
  });
  return (
    <LoadGate state={state} now={now} what="installed apps" onRetry={onRetry}>
      {view === 'updates' && updates.length > 0 && (
        <div className="om-store-batch">
          <p>
            <strong>
              {updates.length} {updates.length === 1 ? 'update' : 'updates'} available.
            </strong>{' '}
            Each update snapshots the app first and reverts on its own if the app is not healthy afterwards.
          </p>
          <Button variant="primary" icon="updates" disabled={stale} onClick={() => setBatch(true)}>
            Request all updates
          </Button>
          <RequestDialog
            open={batch}
            onClose={() => setBatch(false)}
            title={`Request ${updates.length} updates`}
            req={batchReq}
            confirmLabel="Send one request"
            onConfirm={() => {
              onRequest(batchReq);
              setBatch(false);
            }}
          >
            <ul className="om-perm-list">
              {updates.map((u) => (
                <li key={u.app.id}>
                  {u.app.name}: {u.app.version} → {u.update!.version}
                </li>
              ))}
            </ul>
          </RequestDialog>
        </div>
      )}
      {shown.length === 0 ? (
        view === 'updates' ? (
          <EmptyState icon="check" title="Everything is up to date" command="onemind apps list --updates">
            <p>New versions show up here after they pass the Market's scan.</p>
          </EmptyState>
        ) : (
          <EmptyState icon="apps" title="No apps installed yet" command="onemind apps list --installed">
            <p>Pick one in the Market. Installing asks an owner for approval first.</p>
          </EmptyState>
        )
      ) : (
        <ul className="om-store-installed" aria-label={view === 'updates' ? 'Apps with updates' : 'Installed apps'}>
          {shown.map((inst) => {
            const sv = appStateView(inst, now);
            const job = jobs.find((j) => j.app_id === inst.app.id && isJobActive(j.state));
            const up = hasUpdate(inst.app.version, inst.update);
            return (
              <li key={inst.app.id} className={cx('om-store-irow', !sv.live && 'om-store-irow-stale')}>
                <AppTile app={inst.app} size={44} />
                <div className="om-store-irow-main">
                  <a className="om-store-irow-name" href={manageHref(inst.app.id)}>
                    {inst.app.name}
                  </a>
                  <span className="om-hint">
                    {inst.app.version}
                    {up && ` → ${inst.update!.version}`} · on {inst.node}
                  </span>
                  {view === 'updates' && up && inst.update!.notes[0] && <span className="om-store-irow-note">{inst.update!.notes[0]}</span>}
                  <InstalledKind inst={inst} />
                </div>
                <div className="om-store-irow-state">
                  {job ? <StatusPill tone="info" label="Request in progress" pulse /> : <StatusPill tone={sv.tone} label={sv.label} detail={sv.detail} />}
                  {up && <StatusPill tone="info" label="Update" dot={false} />}
                </div>
                <div className="om-store-irow-actions">
                  {inst.url ? (
                    <Button size="sm" icon="external" disabled={inst.state === 'stopped'} title={inst.state === 'stopped' ? 'Stopped: start it from Manage first' : undefined} onClick={() => onOpen(inst)}>
                      Open<span className="om-visually-hidden"> {inst.app.name}</span>
                    </Button>
                  ) : (
                    // A disabled "Open" never said why; a service with no web page says so instead (PRINCIPLES P1).
                    <span className="om-store-noweb">No web page</span>
                  )}
                  <a className="om-btn om-btn-ghost om-btn-sm" href={manageHref(inst.app.id)}>
                    Manage<span className="om-visually-hidden"> {inst.app.name}</span>
                  </a>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </LoadGate>
  );
}

// ---------------------------------------------------------------- manage one app

export interface ManageAppProps {
  inst?: InstalledApp;
  state: LoadState;
  now: number;
  isOwner: boolean;
  job?: StoreJob;
  logs: LogLine[];
  logState: LoadState;
  backHref: string;
  storeHref?: (id: string) => string;
  onOpen: (inst: InstalledApp) => void;
  onRequest: (req: StoreActionRequest) => void;
  onCopied?: (label: string) => void;
  initialTab?: string;
  /**
   * For a hub that cannot keep an app's data on removal (contract v0 deletes the app's namespace):
   * this sentence replaces the keep/delete choice in the remove dialog, and the request carries
   * only `app_id`, so the dialog never promises that the data is kept.
   */
  removeNote?: string;
}

type Pending = { type: StoreActionType } | null;

export function ManageApp({ inst, state, now, isOwner, job, logs, logState, backHref, storeHref, onOpen, onRequest, onCopied, initialTab, removeNote }: ManageAppProps) {
  const [pending, setPending] = useState<Pending>(null);
  const [keep, setKeep] = useState(true);
  const [typed, setTyped] = useState('');
  // Phones: Open stays visible, the rest sit behind "More actions" (CRITIQUE #22).
  const [more, setMore] = useState(false);
  const moreId = useId();
  const close = () => {
    setPending(null);
    setKeep(true);
    setTyped('');
  };
  return (
    <div className="om-store om-store-detail">
      <a className="om-store-back" href={backHref}>
        <CategoryIcon name="chevronLeft" size={16} /> Installed apps
      </a>
      <LoadGate state={state} now={now} what="app">
        {!inst ? (
          <EmptyState icon="apps" title="This app is not installed" command="onemind apps list --installed">
            <p>It may have been removed. Its data is kept unless someone asked to delete it.</p>
          </EmptyState>
        ) : (
          (() => {
            const app = inst.app;
            const sv = appStateView(inst, now);
            const stale = (state.kind === 'ready' && state.stale) || !sv.live;
            const busy = job && isJobActive(job.state);
            const why = state.kind === 'ready' && state.stale ? 'The hub is not answering. Requests wait until it is back.' : busy ? 'A request for this app is in progress.' : undefined;
            const up = hasUpdate(app.version, inst.update);
            const core = app.deploy_class === 'core';
            const ask = (type: StoreActionType) => () => setPending({ type });
            const req = pending
              ? pending.type === 'app.update'
                ? buildRequest('app.update', app, { to_version: inst.update?.version })
                : pending.type === 'app.remove'
                  ? buildRequest('app.remove', app, removeNote ? {} : { keep_data: keep })
                  : buildRequest(pending.type, app)
              : null;
            const send = (r: StoreActionRequest) => {
              onRequest(r);
              close();
            };
            return (
              <>
                <header className="om-store-detail-hero om-store-manage-hero">
                  <AppTile app={app} size={72} />
                  <div className="om-store-detail-titles">
                    <h1 className="om-store-detail-name">{app.name}</h1>
                    <p className="om-store-detail-meta">
                      <StatusPill tone={sv.tone} label={sv.label} detail={sv.detail} />
                      <span className="om-hint">
                        {app.version} on {inst.node}
                      </span>
                      <ClassPills app={app} />
                    </p>
                    {inst.url && (
                      <p className="om-hint">
                        {inst.url_note ? null : <Icon name="lock" size={14} />} {inst.url.replace(/^https?:\/\//, '')} · {inst.url_note ?? 'behind the OneMind sign-in'}
                      </p>
                    )}
                  </div>
                  <div className="om-store-actionbar" role="group" aria-label={`${app.name} actions`}>
                    <Button variant="primary" icon="external" disabled={!inst.url || inst.state === 'stopped'} onClick={() => onOpen(inst)}>
                      Open
                    </Button>
                    <button type="button" className="om-btn om-btn-secondary om-store-more-toggle" aria-expanded={more} aria-controls={moreId} onClick={() => setMore((m) => !m)}>
                      More actions
                    </button>
                    <div id={moreId} className="om-store-actionbar-more" data-open={more}>
                    <Button disabled={!!why} onClick={ask('app.restart')}>
                      <CategoryIcon name="restart" size={18} />
                      Restart
                    </Button>
                    {inst.state === 'stopped' ? (
                      <Button disabled={!!why} onClick={ask('app.start')}>
                        <CategoryIcon name="play" size={18} />
                        Start
                      </Button>
                    ) : (
                      <Button disabled={!!why || core} onClick={ask('app.stop')}>
                        <CategoryIcon name="stop" size={18} />
                        Stop
                      </Button>
                    )}
                    {up && (
                      <Button disabled={!!why || core} onClick={ask('app.update')}>
                        <Icon name="updates" size={18} />
                        Update to {inst.update!.version}
                      </Button>
                    )}
                    {!core && (
                      <Button variant="ghost" className="om-store-remove" disabled={!!why} onClick={ask('app.remove')}>
                        <CategoryIcon name="trash" size={18} />
                        Remove…
                      </Button>
                    )}
                    </div>
                  </div>
                  {why ? <p className="om-store-cta-why">{why}</p> : <p className="om-hint">Restart, stop, update and remove are sent as requests; an owner approves each one first.</p>}
                  {core && <p className="om-hint">Part of OneMind: it updates with the system and cannot be removed.</p>}
                </header>

                {stale && sv.detail && (
                  <p className="om-note om-tone-warn">The values on this page are its last report ({sv.detail}), not live.</p>
                )}
                {job && <JobProgress job={job} now={now} onOpen={() => onOpen(inst)} />}

                <Tabs
                  label={`${app.name} sections`}
                  initial={initialTab}
                  tabs={[
                    {
                      id: 'overview',
                      label: 'Overview',
                      content: (
                        <div className="om-store-detail-cols">
                          <div className="om-store-col">
                            <CredentialsCard inst={inst} isOwner={isOwner} onCopied={onCopied} />
                            {up && (
                              <Card title={`Update to ${inst.update!.version}`} level={2} subtitle={formatDay(inst.update!.released_at)}>
                                <ReleaseNotes notes={[inst.update!]} />
                              </Card>
                            )}
                          </div>
                          <div className="om-store-col">
                            <Card title="Data" level={2}>
                              <dl className="om-facts">
                                <div>
                                  <dt>Size</dt>
                                  <dd>{inst.data_size ?? 'unknown'}</dd>
                                </div>
                                <div>
                                  <dt>Last backup</dt>
                                  <dd>{inst.last_backup ? formatAgo(secondsSince(inst.last_backup, now)) : 'Never'}</dd>
                                </div>
                                <div>
                                  <dt>Health checked</dt>
                                  <dd>{formatAgo(secondsSince(inst.checked_at, now))}</dd>
                                </div>
                              </dl>
                              {storeHref && <a href={storeHref(app.id)}>Market page, trust and licence</a>}
                            </Card>
                          </div>
                        </div>
                      ),
                    },
                    { id: 'settings', label: 'Settings', content: <SettingsForm inst={inst} onRequest={onRequest} disabled={why} /> },
                    { id: 'logs', label: 'Logs', content: <LogViewer appId={app.id} lines={logs} state={logState} now={now} /> },
                    {
                      id: 'history',
                      label: 'History',
                      content:
                        (inst.history ?? []).length === 0 ? (
                          <EmptyState icon="clock" title="No history yet" />
                        ) : (
                          <ol className="om-store-history">
                            {inst.history!.map((h) => (
                              <li key={h.at + h.text}>
                                <time dateTime={h.at}>{formatDay(h.at)}</time>
                                <span>
                                  {h.text} <span className="om-hint">· {h.by}</span>
                                </span>
                                <StatusPill
                                  tone={h.result === 'succeeded' ? 'ok' : h.result === 'cancelled' ? 'neutral' : 'bad'}
                                  label={h.result === 'rolled_back' ? 'Rolled back' : h.result[0]!.toUpperCase() + h.result.slice(1)}
                                />
                              </li>
                            ))}
                          </ol>
                        ),
                    },
                  ]}
                />

                {req && pending?.type === 'app.remove' && (
                  <RequestDialog
                    open
                    onClose={close}
                    role="alertdialog"
                    title={`Remove ${app.name}?`}
                    req={req}
                    danger={!keep}
                    confirmLabel={keep ? 'Request removal' : 'Request removal and deletion'}
                    confirmDisabled={!keep && typed.trim() !== app.name}
                    onConfirm={() => {
                      send(req);
                      if (!keep) onRequest(buildRequest('app.delete_data', app, { confirm: app.name }));
                    }}
                  >
                    {removeNote ? (
                      <p className="om-note om-tone-warn">{removeNote}</p>
                    ) : (
                      <fieldset className="om-store-choice">
                        <legend>What happens to its data ({inst.data_size ?? 'size unknown'})</legend>
                        <label>
                          <input type="radio" name="om-keep" checked={keep} onChange={() => setKeep(true)} />
                          <span>
                            <strong>Keep the data</strong> (recommended). Reinstalling later picks it up again.
                          </span>
                        </label>
                        <label>
                          <input type="radio" name="om-keep" checked={!keep} onChange={() => setKeep(false)} />
                          <span>
                            <strong>Delete the data too.</strong> This is a second, separate request and cannot be undone after approval.
                          </span>
                        </label>
                      </fieldset>
                    )}
                    {!keep && (
                      <label className="om-store-field">
                        <span>
                          Type <strong>{app.name}</strong> to confirm
                        </span>
                        <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
                      </label>
                    )}
                  </RequestDialog>
                )}
                {req && pending?.type === 'app.update' && (
                  <RequestDialog open onClose={close} title={`Update ${app.name} to ${inst.update?.version}`} req={req} confirmLabel="Request update" onConfirm={() => send(req)}>
                    {inst.update && <ReleaseNotes notes={[inst.update]} />}
                    <ol className="om-store-firstrun">
                      <li>Snapshot its data.</li>
                      <li>Install {inst.update?.version}.</li>
                      <li>Run its health checks on fresh signals.</li>
                      <li>If they fail, put {app.version} and the snapshot back on its own.</li>
                    </ol>
                  </RequestDialog>
                )}
                {req && pending && (pending.type === 'app.restart' || pending.type === 'app.stop' || pending.type === 'app.start') && (
                  <RequestDialog
                    open
                    onClose={close}
                    title={req.summary}
                    req={req}
                    confirmLabel={`Request ${pending.type.slice(4)}`}
                    onConfirm={() => send(req)}
                  >
                    <p>
                      {pending.type === 'app.restart' && `${app.name} restarts. It is unavailable for about a minute.`}
                      {pending.type === 'app.stop' && `${app.name} stops and stays stopped until someone starts it. Its data is kept.`}
                      {pending.type === 'app.start' && `${app.name} starts on ${inst.node}.`}
                    </p>
                  </RequestDialog>
                )}
              </>
            );
          })()
        )}
      </LoadGate>
    </div>
  );
}

/** Category and deployment kind on each installed row, so the list answers "what is this and where did it come from". */
function InstalledKind({ inst }: { inst: InstalledApp }) {
  const cat = CATEGORY_BY_SLUG[inst.app.category as keyof typeof CATEGORY_BY_SLUG];
  return (
    <span className="om-store-irow-kind">
      <span>
        {cat && <CategoryIcon name={cat.icon} size={14} />} {cat?.label ?? 'Uncategorised'}
      </span>
      <ClassPills app={inst.app} />
    </span>
  );
}

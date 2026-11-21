// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from 'react';
import { Card, Icon } from '@onemind/ui';
import { subjectOf, useHub } from '../data/hub';
import { href } from './routes';
import { isActive } from '../data/adapters';
import type { Action } from '../api/types';

export function ActionStatus({ action: a, label = 'Request progress' }: { action: Action; label?: string }) {
  return <Card as="section" title={label} variant="sunken">
    <p role="status">Request status: {a.state.replace(/_/g, ' ')}</p>
    {a.progress && <p>Executor step: {a.progress.step}</p>}
    {a.progress && Number.isFinite(a.progress.pct) && <progress aria-label={`${a.type} progress`} max={100} value={a.progress.pct}>{a.progress.pct}%</progress>}
    {a.result?.message && <p>Gateway result: {a.result.message}</p>}
  </Card>;
}

/** Jobs the tray and the menu-bar ring both list: app requests still in play or just finished. */
function useJobs() {
  const hub = useHub();
  const jobs = hub.actionList.filter((a) => a.type.startsWith('app.') && (isActive(a) || Date.parse(a.updated_at ?? '') > hub.now - 60_000));
  return { hub, jobs };
}

/**
 * The desktop's one place for job progress: a small amber ring beside the bell in the menu bar.
 * It says how many jobs are in play and opens the lead request; it never covers content. Amber is
 * the single "needs you" colour (the bell badge uses it too).
 */
export function JobsRing() {
  const { hub, jobs } = useJobs();
  const active = jobs.filter(isActive);
  if (!active.length) return null;
  const lead = active.find((a) => a.state === 'awaiting_approval') ?? active[0]!;
  const running = active.some((a) => a.state !== 'awaiting_approval');
  const label = `${active.length} ${active.length === 1 ? 'job' : 'jobs'}: ${subjectOf(hub, lead)}, ${lead.state.replace(/_/g, ' ')}`;
  return (
    <a href={href.approval(lead.id)} className={`dsk-jobs${running ? ' dsk-jobs-on' : ''}`} aria-label={label} title={label}>
      <span className="dsk-jobs-ring" aria-hidden="true" />
      <span className="dsk-jobs-count" aria-hidden="true">{active.length}</span>
    </a>
  );
}

/** Show ledger states and executor percentages, never guessed install/health stages. */
export function ActionJobs({ desktop = false }: { desktop?: boolean }) {
  const hub = useHub();
  const [open, setOpen] = useState(false);
  const panel = useId();
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const jobs = hub.actionList.filter((a) => a.type.startsWith('app.') && !dismissed.has(a.id) && (isActive(a) || Date.parse(a.updated_at ?? '') > hub.now - 60_000));
  if (!jobs.length) return null;
  const active = jobs.filter(isActive);
  // On the desktop the menu-bar ring carries "needs you"; the floating pill is only for work that is running.
  if (desktop && !jobs.some((a) => a.state !== 'awaiting_approval')) return null;
  const lead = active.find((a) => a.state !== 'awaiting_approval') ?? active[0] ?? jobs[0]!;
  const state = lead.state.replace(/_/g, ' ');
  return <aside aria-label="Jobs in progress" className={`om-store-tray${desktop ? ' om-store-tray-desk' : ''}${open ? ' om-store-tray-open' : ''}`}>
    {open && <div id={panel} className="om-store-tray-panel"><ul>{jobs.map((a) => <li key={a.id}>
      <div className="om-store-tray-text"><a href={href.approval(a.id)}>{a.type}: {subjectOf(hub, a)}</a><ActionStatus action={a} /></div>
      {!isActive(a) && <button type="button" className="om-icon-btn" aria-label={`Dismiss ${subjectOf(hub, a)}`} onClick={() => setDismissed(new Set(dismissed).add(a.id))}><Icon name="x" size={16} /></button>}
    </li>)}</ul></div>}
    <button type="button" className="om-store-tray-pill" aria-expanded={open} aria-controls={panel} onClick={() => setOpen(!open)}>
      <span className={`om-store-tray-ring${isActive(lead) && lead.state !== 'awaiting_approval' ? ' om-store-tray-ring-on' : ''}`} aria-hidden="true" />
      <span aria-live="polite">{active.length ? `${active.length} ${active.length === 1 ? 'job' : 'jobs'}` : 'Jobs done'} · {subjectOf(hub, lead)}: {state[0]!.toUpperCase() + state.slice(1)}{lead.progress && Number.isFinite(lead.progress.pct) ? ` ${lead.progress.pct}%` : ''}</span>
      <Icon name="chevron" size={16} className={open ? 'om-store-rot' : undefined} />
    </button>
  </aside>;
}

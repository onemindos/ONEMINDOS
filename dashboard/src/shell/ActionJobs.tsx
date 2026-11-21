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

/** Show ledger states and executor percentages, never guessed install/health stages. */
/** `bar`: a compact chip inside the desktop menu bar (the panel drops down); `tray`: the floating pill of the console layout. */
export function ActionJobs({ variant = 'tray' }: { variant?: 'tray' | 'bar' }) {
  const hub = useHub();
  const [open, setOpen] = useState(false);
  const panel = useId();
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const jobs = hub.actionList.filter((a) => a.type.startsWith('app.') && !dismissed.has(a.id) && (isActive(a) || Date.parse(a.updated_at ?? '') > hub.now - 60_000));
  if (!jobs.length) return null;
  const active = jobs.filter(isActive);
  const lead = active.find((a) => a.state !== 'awaiting_approval') ?? active[0] ?? jobs[0]!;
  const state = lead.state.replace(/_/g, ' ');
  const compact = variant === 'bar';
  const count = active.length ? `${active.length} ${active.length === 1 ? 'job' : 'jobs'}` : 'Jobs done';
  return <aside aria-label="Jobs in progress" className={`om-store-tray${open ? ' om-store-tray-open' : ''}${compact ? ' om-store-tray-bar' : ''}`}>
    {open && <div id={panel} className="om-store-tray-panel"><ul>{jobs.map((a) => <li key={a.id}>
      <div className="om-store-tray-text"><a href={href.approval(a.id)}>{a.type}: {subjectOf(hub, a)}</a><ActionStatus action={a} /></div>
      {!isActive(a) && <button type="button" className="om-icon-btn" aria-label={`Dismiss ${subjectOf(hub, a)}`} onClick={() => setDismissed(new Set(dismissed).add(a.id))}><Icon name="x" size={16} /></button>}
    </li>)}</ul></div>}
    <button type="button" className="om-store-tray-pill" aria-expanded={open} aria-controls={panel} onClick={() => setOpen(!open)}>
      <span className={`om-store-tray-ring${isActive(lead) && lead.state !== 'awaiting_approval' ? ' om-store-tray-ring-on' : ''}`} aria-hidden="true" />
      {compact
        ? <span aria-live="polite">{count}<span className="om-visually-hidden"> · {subjectOf(hub, lead)}: {state[0]!.toUpperCase() + state.slice(1)}</span></span>
        : <span aria-live="polite">{count} · {subjectOf(hub, lead)}: {state[0]!.toUpperCase() + state.slice(1)}{lead.progress && Number.isFinite(lead.progress.pct) ? ` ${lead.progress.pct}%` : ''}</span>}
      <Icon name="chevron" size={16} className={open ? 'om-store-rot' : undefined} />
    </button>
  </aside>;
}

// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { useHub } from '../data/hub';
import { href } from './routes';
import { isActive } from '../data/adapters';
import type { Action } from '../api/types';

export function ActionStatus({ action: a, label = 'Request progress' }: { action: Action; label?: string }) {
  return <section aria-label={label}><p role="status">{a.state.replace(/_/g, ' ')}{a.progress ? ` — ${a.progress.step}` : ''}</p>
    {a.progress && Number.isFinite(a.progress.pct) && <progress aria-label={`${a.type} progress`} max={100} value={a.progress.pct}>{a.progress.pct}%</progress>}
    {a.result?.message && <p>{a.result.message}</p>}
  </section>;
}

/** Show ledger states and executor percentages, never guessed install/health stages. */
export function ActionJobs() {
  const hub = useHub();
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const jobs = hub.actionList.filter((a) => a.type.startsWith('app.') && !dismissed.has(a.id) && (isActive(a) || Date.parse(a.updated_at ?? '') > hub.now - 60_000));
  if (!jobs.length) return null;
  return <aside aria-label="Jobs in progress" className="om-store-tray"><ul>{jobs.map((a) => <li key={a.id}>
    <a href={href.approval(a.id)}>{a.type}: {hub.appName(a.params.app_id)}</a>
    <ActionStatus action={a} />
    {!isActive(a) && <button type="button" onClick={() => setDismissed(new Set(dismissed).add(a.id))}>Dismiss {hub.appName(a.params.app_id)}</button>}
  </li>)}</ul></aside>;
}

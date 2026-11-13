// SPDX-License-Identifier: Apache-2.0
// Restore: ask first, see the plan, then follow it. A whole-app restore needs the app's id typed
// (it stops the app and replaces its data); one file does not. Either way the request waits in
// Approvals, and the hub saves today's data first so the restore itself can be undone.
import { useId, useState } from 'react';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { StatusPill } from '../components/StatusPill';
import { formatAgo, secondsSince } from '../lib/time';
import { restoreConfirmed, restoreRequest } from './logic';
import './backups.css';
import type { Restore, Snapshot } from './types';

export interface RestoreDialogProps {
  open: boolean;
  snapshot: Snapshot;
  scope: { app_id: string; path?: string };
  now: number;
  onClose: () => void;
  /** Sends POST /v1/restores with this body; the caller shows the result as a RestoreProgress. */
  onRequest: (body: ReturnType<typeof restoreRequest>['body']) => void;
  busy?: boolean;
  showEquivalent?: boolean;
}

export function RestoreDialog(p: RestoreDialogProps) {
  const id = useId();
  const [typed, setTyped] = useState('');
  const [reason, setReason] = useState('');
  const req = restoreRequest(p.snapshot.id, p.scope, reason.trim() || undefined);
  const whole = p.scope.path === undefined;
  const ok = restoreConfirmed(p.scope, typed);
  return (
    <Dialog
      open={p.open}
      onClose={p.onClose}
      role="alertdialog"
      size="lg"
      title={whole ? `Restore ${p.scope.app_id}` : 'Put one item back'}
      description={`From the backup taken ${formatAgo(secondsSince(p.snapshot.taken_at, p.now))} (${p.snapshot.taken_at.slice(0, 16).replace('T', ' ')} UTC).`}
      actions={
        <>
          <Button onClick={p.onClose}>Cancel</Button>
          <Button variant="danger" disabled={!ok} busy={p.busy} onClick={() => p.onRequest(req.body)}>
            Request restore
          </Button>
        </>
      }
    >
      <ol className="omb-plan">
        <li>Today’s data is saved first, as an undo point.</li>
        {whole ? (
          <>
            <li>{p.scope.app_id} stops for a few minutes.</li>
            <li>Its files{' '}and its database go back to that moment. Anything newer is replaced, but stays in the undo point.</li>
            <li>It starts again. If it does not come back healthy, today’s data is put back automatically.</li>
          </>
        ) : (
          <li>
            <code>{p.scope.path}</code> goes back to that moment. The app keeps running.
          </li>
        )}
        <li>Nothing happens until you approve the request.</li>
      </ol>
      <label className="omb-field" htmlFor={`${id}-reason`}>
        <span>Why (optional, kept with the request)</span>
        <input id={`${id}-reason`} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </label>
      {whole && (
        <label className="omb-field" htmlFor={`${id}-confirm`}>
          <span>Type <strong>{p.scope.app_id}</strong> to confirm</span>
          <input id={`${id}-confirm`} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} />
        </label>
      )}
      {p.showEquivalent && (
        <details className="omb-equivalent">
          <summary>The same request from a terminal</summary>
          <pre>{req.curl}</pre>
        </details>
      )}
    </Dialog>
  );
}

const STATE: Record<Restore['state'], { tone: 'ok' | 'warn' | 'bad' | 'info' | 'neutral'; label: string }> = {
  awaiting_approval: { tone: 'warn', label: 'Waiting for approval' },
  running: { tone: 'info', label: 'Restoring' },
  succeeded: { tone: 'ok', label: 'Restored and healthy' },
  failed: { tone: 'bad', label: 'Not restored · previous data kept' },
  outcome_unknown: { tone: 'bad', label: 'Check the app' },
  cancelled: { tone: 'neutral', label: 'Denied' },
  expired: { tone: 'neutral', label: 'Expired' },
};

/** Follows one restore: plan, steps as they happen, the health gate, and the undo point. */
export function RestoreProgress({ restore, now, onUndo }: { restore: Restore; now: number; onUndo?: (preRestoreSnapshotId: string) => void }) {
  const s = STATE[restore.state];
  return (
    <section className="omb-progress" aria-live="polite" aria-labelledby={`omb-r-${restore.id}`}>
      <h2 id={`omb-r-${restore.id}`} className="omb-subtitle">{restore.plan.summary}</h2>
      <StatusPill tone={s.tone} label={s.label} pulse={restore.state === 'running'} />
      <ol className="omb-steps">
        {restore.steps.map((st) => (
          <li key={`${st.at}-${st.step}`}>
            <span>{st.step}</span> <span className="om-hint">{formatAgo(secondsSince(st.at, now))}</span>
          </li>
        ))}
      </ol>
      {restore.health_gate && (
        <p className="om-hint">
          Health check on fresh pods: {restore.health_gate.verdict === 'pass' ? 'passed' : 'did not pass'}
        </p>
      )}
      {restore.error && <p className="omb-error">{restore.error}</p>}
      {restore.pre_restore_snapshot_id && restore.state === 'succeeded' && onUndo && (
        <Button size="sm" onClick={() => onUndo(restore.pre_restore_snapshot_id!)}>Undo this restore…</Button>
      )}
    </section>
  );
}

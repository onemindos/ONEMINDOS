// SPDX-License-Identifier: Apache-2.0
// Live progress for a request: awaiting approval → pulling image → starting → healthy | rolled back
// (PU-06, PD-03). JobProgress is the full track for the app page; JobsTray is the floating island
// that follows the person across screens. Both render the action record; neither decides.
import { useId, useState } from 'react';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { formatAgo, secondsSince } from '../lib/time';
import { AppTile } from './bits';
import { INSTALL_STEPS, isJobActive, JOB_LABEL, JOB_TONE, jobPercent, jobStepIndex } from './logic';
import type { StoreJob } from './types';

const TERMINAL_TEXT: Partial<Record<StoreJob['state'], string>> = {
  rolled_back: 'It did not become healthy, so OneMind put the previous state back. Nothing was lost.',
  failed: 'The request failed. The hub message is below.',
  denied: 'The owner denied this request. Nothing changed.',
  expired: 'Nobody approved this request in time. Nothing changed.',
};

export function JobProgress({ job, now, onOpen, approvalsHref = '#/approvals' }: { job: StoreJob; now: number; onOpen?: () => void; approvalsHref?: string }) {
  const at = jobStepIndex(job.state);
  const pct = jobPercent(job);
  const failed = job.state === 'rolled_back' || job.state === 'failed';
  const stopped = job.state === 'denied' || job.state === 'expired';
  const labelId = useId();
  return (
    <div className={cx('om-store-job', failed && 'om-store-job-failed')}>
      <div className="om-store-job-head">
        <p id={labelId} className="om-store-job-title">
          {job.type === 'app.update' ? 'Update' : 'Install'} of {job.app_name}
        </p>
        <StatusPill tone={JOB_TONE[job.state]} label={JOB_LABEL[job.state]} pulse={isJobActive(job.state) && job.state !== 'awaiting_approval'} />
      </div>
      <ol className="om-store-steps" aria-label="Progress">
        {INSTALL_STEPS.map((s, i) => {
          const done = i < at || (i === at && job.state === 'healthy');
          const current = i === at && !done;
          const bad = current && (failed || stopped);
          const label = bad ? JOB_LABEL[job.state] : s.label;
          return (
            <li
              key={s.state}
              className={cx('om-store-step', done && 'om-store-step-done', current && 'om-store-step-current', bad && 'om-store-step-bad')}
              aria-current={current ? 'step' : undefined}
            >
              <span className="om-store-step-mark" aria-hidden="true">
                {done ? <Icon name="check" size={14} /> : bad ? <Icon name="x" size={14} /> : i + 1}
              </span>
              <span className="om-store-step-label">
                {label}
                <span className="om-visually-hidden">{done ? ' (done)' : current ? ' (now)' : ' (next)'}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {isJobActive(job.state) && job.state !== 'awaiting_approval' && (
        <div
          className={cx('om-store-bar', pct === undefined && 'om-store-bar-indet')}
          role="progressbar"
          aria-labelledby={labelId}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-valuetext={pct === undefined ? `${JOB_LABEL[job.state]}, progress not reported yet` : `${JOB_LABEL[job.state]}, ${pct} percent`}
        >
          <span style={pct === undefined ? undefined : { width: `${pct}%` }} />
        </div>
      )}
      <p className="om-hint" aria-live="polite">
        {job.state === 'awaiting_approval' ? (
          <>
            Waiting in <a href={approvalsHref}>Approvals</a>. Nothing is downloaded until an owner approves.
          </>
        ) : (
          (TERMINAL_TEXT[job.state] ?? job.message ?? JOB_LABEL[job.state])
        )}
        {job.message && TERMINAL_TEXT[job.state] && <span className="om-store-job-msg"> {job.message}</span>}
        <span className="om-store-job-age"> · updated {formatAgo(secondsSince(job.updated_at, now))}</span>
      </p>
      {job.state === 'healthy' && onOpen && (
        <Button variant="primary" icon="external" onClick={onOpen}>
          Open {job.app_name}
        </Button>
      )}
    </div>
  );
}

/** The floating island (umbrelOS pattern, studied only): a compact summary that expands to the list. */
export function JobsTray({ jobs, now, onDismiss }: { jobs: StoreJob[]; now: number; onDismiss?: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  if (jobs.length === 0) return null;
  const active = jobs.filter((j) => isJobActive(j.state));
  const lead = active.find((j) => j.state !== 'awaiting_approval') ?? active[0] ?? jobs[0]!;
  const pct = jobPercent(lead);
  return (
    <aside className={cx('om-store-tray', open && 'om-store-tray-open')} aria-label="Jobs in progress">
      {open && (
        <div id={panel} className="om-store-tray-panel">
          <ul>
            {jobs.map((j) => (
              <li key={j.action_id}>
                <AppTile app={{ id: j.app_id, name: j.app_name }} size={32} />
                <span className="om-store-tray-text">
                  <strong>{j.app_name}</strong>
                  <span className="om-hint">
                    {JOB_LABEL[j.state]}
                    {jobPercent(j) !== undefined && isJobActive(j.state) && j.state !== 'awaiting_approval' ? ` · ${jobPercent(j)}%` : ''}
                    {' · '}
                    {formatAgo(secondsSince(j.updated_at, now))}
                  </span>
                </span>
                {!isJobActive(j.state) && onDismiss && (
                  <button type="button" className="om-icon-btn" aria-label={`Dismiss ${j.app_name}`} onClick={() => onDismiss(j.action_id)}>
                    <Icon name="x" size={16} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <button type="button" className="om-store-tray-pill" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)}>
        <span className={cx('om-store-tray-ring', isJobActive(lead.state) && lead.state !== 'awaiting_approval' && 'om-store-tray-ring-on')} aria-hidden="true" />
        <span aria-live="polite">
          {active.length > 0 ? `${active.length} ${active.length === 1 ? 'job' : 'jobs'}` : 'Jobs done'} · {lead.app_name}: {JOB_LABEL[lead.state]}
          {pct !== undefined && isJobActive(lead.state) && lead.state !== 'awaiting_approval' ? ` ${pct}%` : ''}
        </span>
        <Icon name="chevron" size={16} className={open ? 'om-store-rot' : undefined} />
      </button>
    </aside>
  );
}

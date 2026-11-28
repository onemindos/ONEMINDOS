// SPDX-License-Identifier: Apache-2.0
import { StatusPill } from '../components/StatusPill';

const LABELS = { alerts: 'Alerts', approvals: 'Approvals', apps: 'Apps', storage: 'Storage', backups: 'Backups', updates: 'Updates', mesh: 'Mesh' };
type Source = keyof typeof LABELS;
type State = 'ok' | 'attention' | 'critical' | 'unknown';
type Reading = { state: State; observed_at: string | null; summary: string };
type HomeStatus = Partial<Record<Source, Reading>>;
export type HomeStatusRow = { source: Source; label: string; state: State; summary: string };
const TONES = { ok: 'ok', attention: 'warn', critical: 'bad', unknown: 'neutral' } as const;
const WORDS = { ok: 'OK', attention: 'Needs attention', critical: 'Critical', unknown: 'Unknown' } as const;

export function statusRows(status: HomeStatus | null): HomeStatusRow[] {
  return (Object.keys(LABELS) as Source[]).map((source) => {
    const reading = status?.[source];
    const observed = reading?.observed_at && Number.isFinite(Date.parse(reading.observed_at));
    const state = observed ? reading.state : 'unknown';
    return { source, label: LABELS[source], state, summary: observed || reading?.state === 'unknown' ? reading.summary : '' };
  });
}

export function BoxHealth({ rows, links, details }: {
  rows: HomeStatusRow[]; links: Partial<Record<Source, string>>; details?: Partial<Record<Source, string>>;
}) {
  // No source has reported (the status read failed, or the box has not answered yet): one line, not seven "Unknown" pills.
  if (rows.length > 0 && rows.every((row) => row.state === 'unknown')) {
    return (
      <section className="omh-section dash-health" aria-label="Box health">
        <div className="omh-section-head"><h2>Box health</h2></div>
        <ul><li><span className="dash-health-row">
          <StatusPill tone="neutral" label={WORDS.unknown} />
          <span>The box has not reported its status yet.</span>
        </span></li></ul>
      </section>
    );
  }
  return (
    <section className="omh-section dash-health" aria-label="Box health">
      <div className="omh-section-head"><h2>Box health</h2></div>
      <ul>{rows.map((row) => {
        const detail = row.state !== 'unknown' && details?.[row.source];
        const body = (
          <>
            <span className="dash-health-label">{row.label}</span>
            <StatusPill tone={TONES[row.state]} label={WORDS[row.state]} />
            {row.summary && <span>{row.summary}</span>}
            {detail && detail !== row.summary && <small>{detail}</small>}
          </>
        );
        return (
          <li key={row.source}>
            {links[row.source] ? <a href={links[row.source]}>{body}</a> : <span className="dash-health-row">{body}</span>}
          </li>
        );
      })}</ul>
    </section>
  );
}

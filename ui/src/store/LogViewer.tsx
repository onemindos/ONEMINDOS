// SPDX-License-Identifier: Apache-2.0
// Per-app logs (PD-08, UX-P4; PROPOSED `GET /v1/apps/{id}/logs`). Filters by level and text,
// and says honestly how old the newest line is when the source stops reporting.
import { useId, useMemo, useState } from 'react';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { cx } from '../lib/cx';
import { freshness } from '../lib/freshness';
import { formatAgo, secondsSince } from '../lib/time';
import { LoadGate } from './bits';
import type { LoadState, LogLine } from './types';

const LEVELS = ['all', 'warn', 'error'] as const;
type LevelFilter = (typeof LEVELS)[number];
const RANK = { debug: 0, info: 1, warn: 2, error: 3 } as const;

export function filterLogs(lines: readonly LogLine[], level: LevelFilter, q: string): LogLine[] {
  const min = level === 'all' ? 0 : RANK[level];
  const needle = q.trim().toLowerCase();
  return lines.filter((l) => RANK[l.level] >= min && (!needle || l.text.toLowerCase().includes(needle)));
}

export function LogViewer({ appId, lines, state, now }: { appId: string; lines: LogLine[]; state: LoadState; now: number }) {
  const [level, setLevel] = useState<LevelFilter>('all');
  const [q, setQ] = useState('');
  const shown = useMemo(() => filterLogs(lines, level, q), [lines, level, q]);
  const id = useId();
  const newest = lines[lines.length - 1];
  const age = newest ? secondsSince(newest.at, now) : Number.NaN;
  const fresh = freshness(age, { staleAfter: 120, offlineAfter: 900 });
  const download = () => {
    const blob = new Blob([lines.map((l) => `${l.at} ${l.level.toUpperCase()} ${l.text}`).join('\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${appId}-logs.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <LoadGate state={state} now={now} what="logs">
      <div className="om-store-logbar">
        <fieldset className="om-segmented">
          <legend className="om-visually-hidden">Level</legend>
          {LEVELS.map((l) => (
            <label key={l} className={cx(level === l && 'om-seg-on')}>
              <input type="radio" name={`${id}-lvl`} checked={level === l} onChange={() => setLevel(l)} />
              {l === 'all' ? 'All' : l === 'warn' ? 'Warnings+' : 'Errors'}
            </label>
          ))}
        </fieldset>
        <label className="om-store-search om-store-search-sm">
          <span className="om-visually-hidden">Filter log lines</span>
          <input type="search" placeholder="Filter lines" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <Button size="sm" onClick={download} disabled={lines.length === 0}>
          Download
        </Button>
      </div>
      {newest && fresh !== 'live' && (
        <p className="om-note om-tone-warn">Newest line is from {formatAgo(age)}. The app may have stopped writing, or the node is not reporting.</p>
      )}
      {lines.length === 0 ? (
        <EmptyState icon="info" title="No log lines yet" command={`onemind apps logs ${appId}`}>
          <p>The app has not written anything since it started.</p>
        </EmptyState>
      ) : (
        <div className="om-store-logs" role="log" aria-label={`Logs for ${appId}`} tabIndex={0}>
          {shown.length === 0 && <p className="om-hint">No lines match.</p>}
          {shown.map((l, i) => (
            <p key={i} className={cx('om-store-logline', `om-store-log-${l.level}`)}>
              <time dateTime={l.at}>{l.at.slice(11, 19)}</time>
              <span className="om-store-loglvl">{l.level.toUpperCase()}</span>
              <span>{l.text}</span>
            </p>
          ))}
        </div>
      )}
    </LoadGate>
  );
}

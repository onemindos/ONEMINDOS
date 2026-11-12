// SPDX-License-Identifier: Apache-2.0
// Activity: the hash-chained audit log as a timeline (contract §3 audit, SECURITY §3.7, UX-B1).
import { useId, useState } from 'react';
import { formatAgo, secondsSince } from '../lib/time';
import { Button } from '../components/Button';
import { PageHeader } from '../components/AppShell';
import { StatusPill } from '../components/StatusPill';
import type { Tone } from '../tokens/tokens';
import { chainBadge, filterAudit, groupByDay, type ActorFilter } from './logic';
import { Async, CallHint, Empty, SetIcon } from './primitives';
import type { ActivityData, AuditEntry, Loadable } from './types';

const FILTERS: Array<[ActorFilter, string]> = [
  ['all', 'Everything'],
  ['person', 'People'],
  ['agent', 'Agents'],
  ['system', 'System'],
];
const ACTOR_TONE: Record<AuditEntry['actor']['kind'], Tone> = { person: 'neutral', agent: 'agent', system: 'info', device: 'info' };
const KIND_ICON = { request: 'plus', decision: 'approvals', result: 'check', 'sign-in': 'key', config: 'settings', checkpoint: 'hash' } as const;

export interface AuditTimelineProps {
  data: Loadable<ActivityData>;
  now: number;
  onVerify?: () => void;
  onRetry?: () => void;
}

export function AuditTimeline({ data, now, onVerify, onRetry }: AuditTimelineProps) {
  const [actor, setActor] = useState<ActorFilter>('all');
  const [q, setQ] = useState('');
  const searchId = useId();
  return (
    <>
      <PageHeader
        title="Activity"
        lede="Every request, decision and result, newest first. Each entry is chained to the one before it, so nothing can be removed or edited quietly."
        actions={
          onVerify && (
            <Button icon="lock" onClick={onVerify} disabled={data.status !== 'ready' || data.stale}>
              Verify the chain
            </Button>
          )
        }
      />
      <Async value={data} label="activity" now={now} onRetry={onRetry} rows={6}>
        {(d) => {
          const badge = chainBadge(d.verify, now);
          const rows = filterAudit(d.entries, actor, q);
          const days = groupByDay(rows, now);
          return (
            <>
              <div className={`om-set-chain om-tone-${badge.tone}`} role={badge.tone === 'bad' ? 'alert' : 'status'}>
                <span className="om-set-chain-icon" aria-hidden="true">
                  <SetIcon name={badge.tone === 'bad' ? 'alert' : 'lock'} size={22} />
                </span>
                <div>
                  <p className="om-set-chain-title">{badge.label}</p>
                  <p className="om-set-chain-text">
                    {badge.detail}
                    {d.verify.checkpoint && d.verify.state !== 'broken' && ` Signed checkpoint #${d.verify.checkpoint.seq.toLocaleString('en-US')} is also kept on ${d.verify.checkpoint.storedOff}, so a rewrite of the whole log would show.`}
                  </p>
                </div>
              </div>
              <div className="om-set-filters">
                <div className="om-set-chips" role="group" aria-label="Show entries from">
                  {FILTERS.map(([k, label]) => (
                    <button key={k} type="button" className="om-set-chip" aria-pressed={actor === k} onClick={() => setActor(k)}>
                      {label}
                    </button>
                  ))}
                </div>
                <label className="om-set-search om-set-search-inline" htmlFor={searchId}>
                  <SetIcon name="search" size={18} />
                  <span className="om-visually-hidden">Search activity</span>
                  <input id={searchId} type="search" placeholder="App, node, #number…" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
                </label>
              </div>
              <p className="om-visually-hidden" role="status">
                {rows.length} entries shown
              </p>
              {days.length === 0 ? (
                <Empty icon="activity" title={d.entries.length === 0 ? 'Nothing has happened yet' : 'No entries match'} command="GET /v1/audit?after=0">
                  {d.entries.length === 0 ? 'Requests, decisions and sign-ins appear here as they happen.' : 'Try another filter or clear the search.'}
                </Empty>
              ) : (
                days.map((day) => (
                  <section key={day.key} className="om-set-day" aria-labelledby={`day-${day.key}`}>
                    <h2 id={`day-${day.key}`} className="om-set-day-title">
                      {day.label}
                    </h2>
                    <ol className="om-set-timeline">
                      {day.items.map((e) => (
                        <li key={e.seq} className="om-set-entry" data-kind={e.kind}>
                          <span className={`om-set-entry-dot om-tone-${ACTOR_TONE[e.actor.kind]}`} aria-hidden="true">
                            <SetIcon name={KIND_ICON[e.kind]} size={14} />
                          </span>
                          <div className="om-set-entry-main">
                            <p className="om-set-entry-text">
                              <StatusPill tone={ACTOR_TONE[e.actor.kind]} label={e.actor.id} dot={false} /> {e.text}
                            </p>
                            <p className="om-set-meta">
                              <time dateTime={e.at}>{formatAgo(secondsSince(e.at, now))}</time> · #{e.seq}
                              {e.node && ` · ${e.node}`}
                              {e.app && ` · ${e.app}`} · <span className="om-set-hash" title="Start of this entry's hash">{e.hash}</span>
                            </p>
                          </div>
                          {e.result && <StatusPill tone={e.result} label={e.resultLabel ?? ''} />}
                        </li>
                      ))}
                    </ol>
                  </section>
                ))
              )}
            </>
          );
        }}
      </Async>
      <CallHint calls={['onemind audit verify', 'GET /v1/audit?after=<seq>', 'GET /v1/audit/verify']} />
    </>
  );
}

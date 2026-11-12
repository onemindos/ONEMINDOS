// SPDX-License-Identifier: Apache-2.0
// Activity (IA §2.5): the audit chain as a readable timeline (backlog UX-B1).
import { useState } from 'react';
import { Card, Icon, PageHeader, StatusPill, formatAgo, secondsSince } from '../../../src';
import { ACTOR_TONE } from '../bits';
import { NOW, activity, type ActorKind } from '../fixtures';

const FILTERS: Array<[ActorKind | 'all', string]> = [
  ['all', 'Everything'],
  ['person', 'People'],
  ['agent', 'Agents'],
  ['system', 'System'],
];

export function Activity() {
  const [f, setF] = useState<ActorKind | 'all'>('all');
  const rows = activity.filter((e) => f === 'all' || e.kind === f);
  return (
    <>
      <PageHeader title="Activity" lede="Every request, decision and result, newest first. Each entry is chained to the one before it, so nothing can be removed quietly." />
      <div className="d-banner om-tone-ok" role="status">
        <Icon name="lock" />
        <span>
          <strong>Chain verified</strong> · 1,284 entries checked 2 min ago, from the first entry to #1284. No gaps, no edits.
        </span>
      </div>
      <div className="d-row" role="group" aria-label="Show">
        {FILTERS.map(([k, label]) => (
          <button key={k} type="button" className="d-chip" aria-pressed={f === k} onClick={() => setF(k)}>
            {label}
          </button>
        ))}
      </div>
      <Card>
        <ol className="d-list" reversed>
          {rows.map((e) => (
            <li key={e.seq}>
              <span className="d-time">
                <time dateTime={e.at}>{formatAgo(secondsSince(e.at, NOW))}</time>
              </span>
              <span className="d-list-main">
                <StatusPill tone={ACTOR_TONE[e.kind]} label={e.actor} dot={false} /> {e.text}
                <span className="d-list-meta"> · #{e.seq}{e.node ? ` · ${e.node}` : ''}{e.app ? ` · ${e.app}` : ''}</span>
              </span>
              {e.result && <StatusPill tone={e.result} label={e.resultLabel ?? ''} />}
            </li>
          ))}
        </ol>
      </Card>
    </>
  );
}

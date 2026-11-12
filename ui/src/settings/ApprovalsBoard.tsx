// SPDX-License-Identifier: Apache-2.0
// Approvals, redesigned: a queue on the left, the selected request on the right with the
// effects card the gateway computed for it (DASHBOARD §3.2 plan card, APP-B3). The UI renders
// the plan; it never decides what a request does.
import { useState } from 'react';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { PageHeader } from '../components/AppShell';
import { ACTION_STATE, ApprovalCard, actionTitle, requesterPill, type ActionSummary, type ApprovalCardProps } from '../components/ApprovalCard';
import { StatusPill } from '../components/StatusPill';
import { RISK, UNDO_TEXT, groupEffects, planRisk } from './logic';
import { Async, CallHint, Empty, Skeleton, SetIcon } from './primitives';
import { CATEGORY_LABEL, DEPLOY_CLASS } from './taxonomy';
import type { ActionPlan, Loadable } from './types';

/* ---------- effects card ---------- */
export function EffectsCard({ plan, now }: { plan: Loadable<ActionPlan>; now: number }) {
  if (plan.status === 'loading') return <Skeleton rows={3} label="what this request will do" />;
  if (plan.status === 'error')
    return (
      <p className="om-note om-tone-bad" role="alert">
        The gateway could not compute what this request will do ({plan.error.error}: {plan.error.message}). Approve only if you know what it does.
      </p>
    );
  const p = plan.data;
  const risk = planRisk(p);
  const groups = groupEffects(p.effects);
  return (
    <section className={`om-set-effects${plan.stale ? ' om-set-stale' : ''}`} aria-label="What will happen">
      <header className="om-set-effects-head">
        <h4>What will happen</h4>
        <StatusPill tone={RISK[risk].tone} label={RISK[risk].label} />
      </header>
      {p.app && (
        <p className="om-set-effects-app">
          <strong>{p.app.name}</strong> <span className="om-set-meta">{CATEGORY_LABEL[p.app.category]}</span> <StatusPill tone={DEPLOY_CLASS[p.app.deploy_class].tone} label={DEPLOY_CLASS[p.app.deploy_class].label} dot={false} />
          {p.app.plugin && <StatusPill tone="info" label="Plugin: adds to OneMind" dot={false} />}
        </p>
      )}
      {p.placement && (
        <p className={`om-note om-tone-${!p.placement.fits ? 'bad' : p.placement.stale ? 'warn' : 'ok'}`}>
          {p.placement.fits ? (
            <>
              Runs on <strong>{p.placement.node}</strong>
              {p.placement.stale ? ', but its last report is not live' : ''}. {p.placement.reason}
            </>
          ) : (
            <>No node can run this: {p.placement.reason}</>
          )}
        </p>
      )}
      {groups.length === 0 ? (
        <p className="om-hint">No changes beyond the action itself.</p>
      ) : (
        <dl className="om-set-effects-list">
          {groups.map((g) => (
            <div key={g.title} className="om-set-effects-row">
              <dt>{g.title}</dt>
              <dd>
                <ul>
                  {g.items.map((e, i) => (
                    <li key={i} data-risk={e.risk}>
                      {e.risk !== 'low' && <span className="om-visually-hidden">{RISK[e.risk].label}: </span>}
                      {e.label}
                      {e.detail && <span className="om-set-meta"> · {e.detail}</span>}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          ))}
        </dl>
      )}
      {p.scan && (
        <p className="om-set-meta">
          Scanned {formatAgo(secondsSince(p.scan.at, now))}: {p.scan.critical} critical, {p.scan.high} high, malware {p.scan.malware === 'clean' ? 'none found' : 'FOUND'}.
        </p>
      )}
      <p className="om-set-effects-undo">
        <SetIcon name={p.undo === 'one-way' ? 'alert' : 'updates'} size={16} /> {UNDO_TEXT[p.undo]}
      </p>
      <p className="om-set-meta">
        Computed by the gateway {formatAgo(secondsSince(p.computed_at, now))} · approving signs plan <code>{p.plan_hash}</code>
      </p>
    </section>
  );
}

/* ---------- board ---------- */
type From = 'all' | 'agent' | 'person' | 'system';
const fromOf = (a: ActionSummary): Exclude<From, 'all'> => (a.requested_by?.id.startsWith('system:') ? 'system' : a.requested_by?.kind === 'agent' ? 'agent' : 'person');

export interface ApprovalsBoardProps {
  actions: Loadable<ActionSummary[]>;
  plans: Record<string, Loadable<ActionPlan>>;
  /** Recent decisions, newest first. */
  decided?: ActionSummary[];
  now: number;
  canDecide: ApprovalCardProps['canDecide'];
  onApprove?: (a: ActionSummary) => void;
  onDeny?: (a: ActionSummary) => void;
  onRetry?: () => void;
  /** Open with this request selected (deep link from a notification). */
  initialId?: string;
  /**
   * Shown instead of the effects card when the gateway serves no plan for a request (contract v0
   * has no plan route; §12.4 adds `GET /v1/actions/{id}/preview`). Without it a missing plan shows
   * as loading.
   */
  planNote?: string;
  /** The line under the card; defaults to the passkey wording of §12.3. */
  approveHint?: string;
  /** The API calls listed at the bottom; defaults to the §12 set. */
  calls?: string[];
}

export function ApprovalsBoard({ actions, plans, decided = [], now, canDecide, onApprove, onDeny, onRetry, initialId, planNote, approveHint, calls }: ApprovalsBoardProps) {
  const [from, setFrom] = useState<From>('all');
  const [sel, setSel] = useState<string | undefined>(initialId);
  return (
    <>
      <PageHeader title="Approvals" lede="Nothing changes on your box until a person approves it. Agents can ask; they can never approve. Each request shows what the gateway computed it will do." />
      <Async
        value={actions}
        label="requests"
        now={now}
        onRetry={onRetry}
        rows={3}
        isEmpty={(d) => d.length === 0}
        empty={
          <Empty icon="check" title="Nothing is waiting" command="GET /v1/actions?state=awaiting_approval">
            New requests from people, agents and automatic updates appear here and on your phone.
          </Empty>
        }
      >
        {(list, live) => {
          const counts = { all: list.length, agent: 0, person: 0, system: 0 } as Record<From, number>;
          list.forEach((a) => counts[fromOf(a)]++);
          const shown = list.filter((a) => from === 'all' || fromOf(a) === from);
          const current = shown.find((a) => a.id === sel) ?? shown[0];
          return (
            <>
              <h2 className="om-set-board-title">Waiting ({list.length})</h2>
              <div className="om-set-chips" role="group" aria-label="Show requests from">
                {(
                  [
                    ['all', 'All'],
                    ['agent', 'Agents'],
                    ['person', 'People'],
                    ['system', 'System'],
                  ] as Array<[From, string]>
                ).map(([k, label]) => (
                  <button key={k} type="button" className="om-set-chip" aria-pressed={from === k} onClick={() => setFrom(k)}>
                    {label} <span className="om-set-chip-count">{counts[k]}</span>
                  </button>
                ))}
              </div>
              {shown.length === 0 ? (
                <Empty icon="check" title="Nothing from this kind of requester">Other requests are under All.</Empty>
              ) : (
                <div className="om-set-board">
                  <ul className="om-set-queue" aria-label="Waiting requests">
                    {shown.map((a) => {
                      const pl = plans[a.id];
                      const risk = pl?.status === 'ready' ? planRisk(pl.data) : undefined;
                      const who = a.requested_by ? requesterPill(a.requested_by) : undefined;
                      const expired = Date.parse(a.expires_at) <= now;
                      return (
                        <li key={a.id}>
                          <button type="button" className="om-set-qitem" aria-current={current?.id === a.id ? 'true' : undefined} onClick={() => setSel(a.id)}>
                            <span className="om-set-qitem-top">
                              {who && <StatusPill tone={who.tone} label={who.label} dot={false} />}
                              {risk && risk !== 'low' && <StatusPill tone={RISK[risk].tone} label={risk === 'high' ? 'High impact' : 'Check'} />}
                            </span>
                            <span className="om-set-qitem-title">{actionTitle(a)}</span>
                            <span className="om-set-meta">
                              {a.requested_by?.id ?? 'unknown'} · {expired ? 'expired' : `expires ${formatIn(a.expires_at, now)}`}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  {current && (
                    <div className="om-set-detail" aria-live="polite">
                      <ApprovalCard
                        key={current.id}
                        action={current}
                        now={now}
                        canDecide={!live ? { allowed: false, reason: 'The hub is not answering; decisions are paused.' } : canDecide}
                        onApprove={onApprove}
                        onDeny={onDeny}
                        extra={
                          <>
                            {!plans[current.id] && planNote ? <p className="om-note om-tone-info">{planNote}</p> : <EffectsCard plan={plans[current.id] ?? { status: 'loading' }} now={now} />}
                            <p className="om-hint">{approveHint ?? 'Approving asks for your passkey and signs exactly this plan. If the plan changes, the request has to be approved again.'}</p>
                          </>
                        }
                      />
                    </div>
                  )}
                </div>
              )}
            </>
          );
        }}
      </Async>
      {decided.length > 0 && (
        <section className="om-set-group" aria-labelledby="recent-decisions">
          <header className="om-set-group-head">
            <h2 id="recent-decisions" className="om-set-board-title">Recent decisions</h2>
          </header>
          <ul className="om-set-rows om-set-decisions" aria-label="Recent decisions">
            {decided.map((a) => (
              <li key={a.id}>
                <div className="om-set-row">
                  <div className="om-set-row-main">
                    <div className="om-set-row-title">{actionTitle(a)}</div>
                    <div className="om-set-meta">
                      Asked by {a.requested_by?.id ?? 'unknown'} · decided by {a.decided_by?.id ?? '—'} · {formatAgo(secondsSince(a.created_at ?? '', now))}
                      {a.message && ` · ${a.message}`}
                    </div>
                  </div>
                  <div className="om-set-row-trail">
                    <StatusPill tone={ACTION_STATE[a.state].tone} label={ACTION_STATE[a.state].label} />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      <CallHint calls={calls ?? ['GET /v1/actions?state=awaiting_approval', 'GET /v1/actions/{id}/plan', 'POST /v1/actions/{id}/approve-options   (passkey challenge bound to the plan hash)', 'POST /v1/actions/{id}/approve', 'POST /v1/actions/{id}/deny']} />
    </>
  );
}

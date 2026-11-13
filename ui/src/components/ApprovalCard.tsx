// SPDX-License-Identifier: Apache-2.0
// One request waiting for (or past) a human decision (contract §3 actions).
// The card always shows who asked (person or agent), the exact parameters, when it expires,
// and the equivalent CLI/API call (backlog UX-B2). An agent can never approve.
import { useId, type ReactNode } from 'react';
import type { Tone } from '../tokens/tokens';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { Button } from './Button';
import { Card } from './Card';
import { Icon } from './Icon';
import { StatusPill } from './StatusPill';

export type ActionState =
  | 'requested'
  | 'awaiting_approval'
  | 'accepted'
  | 'dispatched'
  | 'succeeded'
  | 'failed'
  | 'outcome_unknown'
  | 'expired'
  | 'cancelled';

export interface ActionSummary {
  id: string;
  type: string;
  params: Record<string, unknown>;
  state: ActionState;
  expires_at: string;
  created_at?: string;
  requested_by?: { id: string; kind: 'person' | 'agent'; role?: string };
  decided_by?: { id: string; kind: 'person' | 'agent' };
  /** Why the requester wants it (agents must say). */
  reason?: string;
  /** Plain-language consequence, e.g. "Downloads 120 MB and starts a web app on port 80". */
  impact?: string;
  /** Failure text from the hub. */
  message?: string;
}

export const ACTION_STATE: Record<ActionState, { tone: Tone; label: string }> = {
  requested: { tone: 'info', label: 'Requested' },
  awaiting_approval: { tone: 'warn', label: 'Awaiting approval' },
  accepted: { tone: 'info', label: 'Approved' },
  dispatched: { tone: 'info', label: 'Running' },
  succeeded: { tone: 'ok', label: 'Done' },
  failed: { tone: 'bad', label: 'Failed' },
  outcome_unknown: { tone: 'bad', label: 'Outcome unknown' },
  expired: { tone: 'neutral', label: 'Expired' },
  cancelled: { tone: 'neutral', label: 'Denied' },
};

const VERB: Record<string, string> = {
  'app.install': 'Install',
  'app.remove': 'Remove',
  'app.update': 'Update',
  'app.restart': 'Restart',
  'os.update': 'Update the OS on',
  'backup.restore': 'Restore',
  'node.join': 'Let join',
  'node.drain': 'Drain',
  'repair.apply': 'Fix',
  'exposure.enable': 'Expose to the internet',
};

export function actionTitle(a: Pick<ActionSummary, 'type' | 'params'>): string {
  const target = (a.params.app_id ?? a.params.node_id ?? a.params.target ?? '') as string;
  return `${VERB[a.type] ?? a.type} ${target}`.trim();
}

/**
 * The same decision without the UI (contract §3). Headless and GUI are equal front doors
 * (REC-W11-20). The `onemind` CLI has no actions verb yet, so this shows the REST call.
 */
export function equivalentCall(a: Pick<ActionSummary, 'id'>, decision: 'approve' | 'deny' = 'approve'): string {
  return `POST /v1/actions/${a.id}/${decision}`;
}

/**
 * Person, agent, or the OS itself. `system:*` ids (updates, repairs, automations) are a
 * proposed principal family (docs/design/IA.md); the contract today has person and agent.
 */
export function requesterPill(who: { id: string; kind: 'person' | 'agent' }): { tone: Tone; label: string } {
  if (who.id.startsWith('system:')) return { tone: 'info', label: 'System' };
  return who.kind === 'agent' ? { tone: 'agent', label: 'AI agent' } : { tone: 'neutral', label: 'Person' };
}

export interface ApprovalCardProps {
  action: ActionSummary;
  now: number;
  /** 'no' with a reason when the viewer may not decide (not the owner, or an agent). */
  canDecide: { allowed: true } | { allowed: false; reason: string };
  onApprove?: (a: ActionSummary) => void;
  onDeny?: (a: ActionSummary) => void;
  busy?: boolean;
  /** Highlight a card the person just created or opened from a notification. */
  highlight?: boolean;
  extra?: ReactNode;
}

export function ApprovalCard({ action, now, canDecide, onApprove, onDeny, busy, highlight, extra }: ApprovalCardProps) {
  const detailsId = useId();
  const title = actionTitle(action);
  const st = ACTION_STATE[action.state];
  const pending = action.state === 'awaiting_approval';
  const expired = Date.parse(action.expires_at) <= now;
  const who = action.requested_by;
  const blocked = !canDecide.allowed ? canDecide.reason : expired ? 'This request has expired and can no longer be approved.' : undefined;
  return (
    <Card
      as="article"
      level={3}
      title={title}
      className={highlight ? 'om-highlight' : undefined}
      variant={pending ? 'attention' : 'default'}
      aside={<StatusPill tone={expired && pending ? 'neutral' : st.tone} label={expired && pending ? 'Expired' : st.label} pulse={action.state === 'dispatched'} />}
      footer={
        pending && (onApprove || onDeny) ? (
          <div className="om-decide">
            <Button variant="primary" icon="check" disabled={!!blocked} busy={busy} aria-label={`Approve ${title}`} onClick={() => onApprove?.(action)} aria-describedby={blocked ? detailsId : undefined}>
              Approve
            </Button>
            <Button variant="secondary" icon="x" disabled={!!blocked || busy} aria-label={`Deny ${title}`} onClick={() => onDeny?.(action)}>
              Deny
            </Button>
            {blocked && (
              <span id={detailsId} className="om-hint">
                {blocked}
              </span>
            )}
          </div>
        ) : undefined
      }
    >
      <p className="om-requester">
        {who ? (
          <>
            <StatusPill {...requesterPill(who)} dot={false} />{' '}
            <strong>{who.id}</strong> asked{action.created_at ? ` ${formatAgo(secondsSince(action.created_at, now))}` : ''}
          </>
        ) : (
          'Requester unknown'
        )}
        {pending && !expired && (
          <span className="om-expires">
            <Icon name="clock" size={16} /> expires {formatIn(action.expires_at, now)}
          </span>
        )}
      </p>
      {action.reason && <blockquote className="om-reason">“{action.reason}”</blockquote>}
      {action.impact && <p className="om-impact">{action.impact}</p>}
      {(action.state === 'failed' || action.state === 'outcome_unknown') && (
        <p className="om-note om-tone-bad">{action.message ? `What the hub reported: ${action.message}` : 'The hub gave no reason.'}</p>
      )}
      <details className="om-details">
        <summary>Exact request and API equivalent</summary>
        <pre className="om-code">{JSON.stringify({ type: action.type, params: action.params }, null, 2)}</pre>
        <pre className="om-code">{equivalentCall(action)}</pre>
      </details>
      {action.decided_by && (
        <p className="om-hint">
          Decided by {action.decided_by.kind} <strong>{action.decided_by.id}</strong>
        </p>
      )}
      {extra}
    </Card>
  );
}

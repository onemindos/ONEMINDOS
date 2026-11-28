// SPDX-License-Identifier: Apache-2.0
// One request waiting for (or past) a human decision (contract §3 actions).
// The card always shows who asked (person or agent), the exact parameters, when it expires,
// and the equivalent CLI/API call (backlog UX-B2). An agent can never approve.
import { useId, type ReactNode } from 'react';
import type { Tone } from '../tokens/tokens';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { Button } from './Button';
import { Card } from './Card';
import { HoldToApprove } from './HoldToApprove';
import { Icon } from './Icon';
import { StatusPill } from './StatusPill';
import { VerificationBadge, type VerificationLevel } from './VerificationBadge';

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
  /** 'name' is the display name (Alex, not usr_8f2c); the id is shown when absent. */
  requested_by?: { id: string; kind: 'person' | 'agent'; role?: string; name?: string };
  decided_by?: { id: string; kind: 'person' | 'agent'; name?: string };
  /** Why the requester wants it (agents must say). */
  reason?: string;
  /** Plain-language consequence, e.g. "Downloads 120 MB and starts a web app on port 80". */
  impact?: string;
  /** Failure text from the hub. */
  message?: string;
  /** What the target is called in the catalog ("Ollama", not its id "ollama"); the id is shown when absent. */
  target_name?: string;
  hold?: { duration: number; plan?: string };
  /** The key level approving needs (approve-options' required_level, D-028). */
  required_level?: VerificationLevel;
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

/**
 * One table: action type -> the request in plain words. A target (an app, a node) is appended when
 * the request has one. A type not listed here gets a readable fallback (actionWords), never the dotted name.
 */
export const ACTION_WORDS: Record<string, string> = {
  'app.install': 'Install',
  'app.remove': 'Remove',
  'app.update': 'Update',
  'app.restart': 'Restart',
  'app.start': 'Start',
  'app.stop': 'Stop',
  'app.configure': 'Change settings of',
  'app.delete_data': 'Delete the data of',
  'os.update': 'Update the OS on',
  'os.update.install': 'Install the OS update',
  'os.rollback': 'Roll the OS back',
  'os.rollout.start': 'Start rolling out the OS update',
  'os.rollout.resume': 'Resume rolling out the OS update',
  'backup.run': 'Back up now',
  'backup.verify': 'Check a backup',
  'backup.restore': 'Restore',
  'backup.content.set': 'Change what is backed up',
  'backup.destination.add': 'Add a backup destination',
  'backup.destination.remove': 'Remove a backup destination',
  'backup.kit.issue': 'Make a recovery kit',
  'node.join': 'Let join',
  'node.drain': 'Drain',
  'node.wake': 'Wake up',
  'node.remove': 'Remove',
  'repair.apply': 'Fix',
  'exposure.enable': 'Expose to the internet',
  'legacy.contact.add': 'Add legacy contact',
  'machine.attach_device': 'Attach a device to a machine',
  'machine.detach_device': 'Detach a device from a machine',
  'plugin.configure': 'Change the settings of a plugin',
  'plugin.invoke': 'Let a plugin act',
  'plugin.key.enroll': 'Trust a new plugin key',
  'plugin.key.revoke': 'Stop trusting a plugin key',
  'tls.acme.set': 'Change automatic certificates',
  'files.grant.create': 'Give access to files',
  'system.restart': 'Restart the hub',
  'system.shutdown': 'Shut the hub down',
  'system.factory_reset': 'Erase the hub and start over',
  'service.restart': 'Restart a hub service',
  'users.invite': 'Invite',
  'users.reinvite': 'Replace invite for',
};

/** Plain words for an action type; an unknown one reads as its dotted name spaced out ("Backup destination add"). */
export function actionWords(type: string): string {
  const known = ACTION_WORDS[type];
  if (known) return known;
  const spaced = type.replace(/[._-]+/g, ' ').trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : 'A request';
}

export function actionTitle(a: Pick<ActionSummary, 'type' | 'params'> & { target_name?: string }): string {
  const target = a.target_name ?? ((a.params.app_id ?? a.params.node_id ?? a.params.target ?? '') as string);
  return (actionWords(a.type) + ' ' + target).trim();
}

/** Who, for people: the display name when the hub told us, else the id. */
export const principalName = (who: { id: string; name?: string }): string => who.name || who.id;

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
  onApprove?: (a: ActionSummary, elapsedMs?: number) => void;
  onDeny?: (a: ActionSummary) => void;
  busy?: boolean;
  /** Highlight a card the person just created or opened from a notification. */
  highlight?: boolean;
  extra?: ReactNode;
  /** Developer-facing notes (spec ids, API paths): shown only inside the collapsed Technical details. */
  technical?: ReactNode;
}

export function ApprovalCard({ action, now, canDecide, onApprove, onDeny, busy, highlight, extra, technical }: ApprovalCardProps) {
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
            {action.hold && !blocked && !busy && onApprove ? (
              <HoldToApprove key={`${action.id}:${action.hold.plan}:${action.hold.duration}`} label={`Hold to approve ${title}`}
                duration={action.hold.duration} requiredLevel={action.required_level} onApprove={(ms) => onApprove(action, ms)} />
            ) : <Button variant="primary" icon="check" disabled={!!blocked || !!action.hold} busy={busy} aria-label={`Approve ${title}`} onClick={() => onApprove?.(action)} aria-describedby={blocked ? detailsId : undefined}>
              Approve
            </Button>}
            <Button variant="secondary" icon="x" disabled={!!blocked || busy} aria-label={`Deny ${title}`} onClick={() => onDeny?.(action)}>
              Deny
            </Button>
            {action.required_level && !(action.hold && !blocked && !busy && onApprove) && (
              <VerificationBadge level={action.required_level} required />
            )}
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
            <strong>{principalName(who)}</strong> asked{action.created_at ? ` ${formatAgo(secondsSince(action.created_at, now))}` : ''}
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
        <summary>Technical details</summary>
        {technical && <p className="om-hint">{technical}</p>}
        <p className="om-hint">The exact request, and the same decision as an API call.</p>
        <pre className="om-code">{JSON.stringify({ type: action.type, params: action.params }, null, 2)}</pre>
        <pre className="om-code">{equivalentCall(action)}</pre>
      </details>
      {action.decided_by && (
        <p className="om-hint">
          Decided by {action.decided_by.kind} <strong>{principalName(action.decided_by)}</strong>
        </p>
      )}
      {extra}
    </Card>
  );
}

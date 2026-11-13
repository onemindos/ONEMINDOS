// SPDX-License-Identifier: Apache-2.0
// Approvals: the queue of requests and the recent decisions. Approving uses the signed-in token
// today (contract §3); passkey approval and the gateway-computed plan come with §12.3 and §12.4.
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { ApprovalsBoard, actionTitle, useToast, type ActionSummary, type SettingsLoadable } from '@onemind/ui';
import { toActionSummary } from '../data/adapters';
import { errorText, useHub } from '../data/hub';

export const PLAN_NOTE =
  'This hub does not compute a plan for requests yet (§12.4, CORE-SANDBOX), so check the exact request above. An app.install or app.remove applies or deletes that app from the Market catalog; an install runs only after its scan check.';
export const APPROVE_HINT = 'Approving uses your sign-in token for now. Passkey approval, bound to the plan, comes with CORE-SEC-2 (§12.3).';

export function Approvals() {
  const hub = useHub();
  const toast = useToast();
  const [params] = useSearchParams();
  const all = hub.actionList.map(toActionSummary);
  const waiting = all.filter((a) => a.state === 'awaiting_approval');
  const decided = all.filter((a) => a.state !== 'awaiting_approval' && a.state !== 'requested').slice(0, 10);
  const stale = hub.freshness === 'stale' || hub.freshness === 'offline';
  const actions: SettingsLoadable<ActionSummary[]> =
    hub.actions.data !== undefined
      ? { status: 'ready', data: waiting, asOf: hub.asOf ?? new Date().toISOString(), stale }
      : hub.actions.error
        ? { status: 'error', error: { error: hub.actions.error.code === 'network' ? 'unavailable' : (hub.actions.error.code as 'not_found'), message: hub.actions.error.message } }
        : { status: 'loading' };

  // What the owner just decided, followed to its end. Written in words as a status line so the
  // outcome is announced even after the request leaves the waiting list.
  const [last, setLast] = useState<{ id: string; title: string }>();
  const lastNow = last ? all.find((a) => a.id === last.id) : undefined;
  const ended = lastNow && !['requested', 'awaiting_approval', 'accepted', 'dispatched'].includes(lastNow.state);

  const decide = (a: ActionSummary, how: 'approve' | 'deny') =>
    void hub.decide(a.id, how).then(
      () => {
        setLast({ id: a.id, title: actionTitle(a) });
        toast.show({ tone: how === 'approve' ? 'ok' : 'neutral', title: how === 'approve' ? 'Approved' : 'Denied', body: how === 'approve' ? 'The hub is applying it. Progress shows on the app page and in the tray.' : 'Nothing changes.' });
      },
      (e: unknown) => {
        const { code, message } = errorText(e);
        toast.show({ tone: 'bad', title: `Could not ${how}`, body: `${message} (${code})` });
      },
    );

  return (
    <>
      {last && lastNow && (
        <p className="om-note om-tone-info" {...(ended ? { role: 'status' } : {})}>
          {last.title}: {ended ? lastNow.state.replace(/_/g, ' ') : 'approved, the hub is applying it'}.
        </p>
      )}
    <ApprovalsBoard
      actions={actions}
      plans={{}}
      planNote={PLAN_NOTE}
      approveHint={APPROVE_HINT}
      calls={['GET /v1/actions', 'POST /v1/actions/{id}/approve', 'POST /v1/actions/{id}/deny']}
      decided={decided}
      now={hub.now}
      canDecide={hub.canDecide === 'no' ? { allowed: false, reason: 'Only the owner can approve or deny. Agents can ask; they can never approve.' } : { allowed: true }}
      onApprove={(a) => decide(a, 'approve')}
      onDeny={(a) => decide(a, 'deny')}
      onRetry={hub.reloadAll}
      initialId={params.get('highlight') ?? undefined}
      key={params.get('highlight') ?? ''}
    />
    </>
  );
}

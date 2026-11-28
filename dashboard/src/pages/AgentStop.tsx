// SPDX-License-Identifier: Apache-2.0
// Settings > Agents: the agent kill switch (CORE-SEC-6, #159), GET/PUT /v1/agents/kill-switch.
// Everyone signed in sees whether AI agents are stopped; only the owner gets the button. The
// gateway is the boundary (it refuses anyone else, and refuses every agent while the switch is
// on); the page only avoids offering what would be refused.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type Action, type components } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { isApprovalRequest } from '../lib/permissions';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load, TextField, useRun } from './parts';

type KillSwitch = components['schemas']['KillSwitch'];
const PATH = '/v1/agents/kill-switch';

async function call(sdk: OneMind, method: 'GET' | 'PUT', body?: components['schemas']['KillSwitchBody']): Promise<KillSwitch | Action> {
  try {
    const v = await sdk.call<KillSwitch | Action>({ method, path: PATH, body });
    if (!v || (!isApprovalRequest(v) && !('on' in v && typeof v.on === 'boolean'))) throw new Error('The hub returned an invalid kill switch state.');
    return v;
  } catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

export function AgentStop() {
  const { token, mock, principal } = useSignedIn();
  if (mock) return null; // demo mode has no gateway to stop agents on
  return <LiveAgentStop token={token} owner={principal?.role === 'owner'} />;
}

function LiveAgentStop({ token, owner }: { token: string; owner: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const state = usePoll(async () => {
    const value = await call(sdk, 'GET');
    if (isApprovalRequest(value)) throw new Error('The hub returned an invalid kill switch state.');
    return value;
  }, 15_000);
  const run = useRun();
  const [confirm, setConfirm] = useState<boolean>();
  const [reason, setReason] = useState('');
  const [deliveryPending, setDeliveryPending] = useState<'fabric_policy_pending' | 'agent_broker_cutoff_pending'>();
  const [pendingResume, setPendingResume] = useState<string>();
  const change = (on: boolean) =>
    void run(async () => {
      setDeliveryPending(undefined);
      setPendingResume(undefined);
      try {
        const result = await call(sdk, 'PUT', { on, ...(reason.trim() ? { reason: reason.trim() } : {}) });
        if (isApprovalRequest(result)) setPendingResume(result.id);
      } catch (error) {
        if (!(error instanceof ApiError) || (error.reason !== 'fabric_policy_pending' && error.reason !== 'agent_broker_cutoff_pending')) throw error;
        setDeliveryPending(error.reason);
      }
      setConfirm(undefined);
      setReason('');
      await state.reload();
    }, on ? 'Stop all AI agents' : 'Request to resume AI agents');

  return (
    <Card title="Agent kill switch" as="article">
      {deliveryPending === 'fabric_policy_pending' && <p className="om-note om-tone-warn" role="alert">The hub stopped agent requests. Fabric confirmation was pending when it replied. Check Machine policy delivery for updates.</p>}
      {deliveryPending === 'agent_broker_cutoff_pending' && <p className="om-note om-tone-warn" role="alert">The hub stopped agent requests. The message broker cutoff is still unconfirmed.</p>}
      {pendingResume && <p role="status">Resume requested. <Link to={href.approval(pendingResume)}>Review in Approvals</Link>.</p>}
      <Load res={state} what="Loading the agent kill switch">
        {(s) => (
          <>
            <p>
              {s.on ? <StatusPill tone="bad" label="Agent requests blocked at the hub" /> : <StatusPill tone="ok" label="Agent requests allowed at the hub" />}{' '}
              {s.on
                ? 'The hub refuses every request from an AI agent, and nothing an agent asked for can be approved, until the owner resumes them.'
                : 'Stopping blocks every AI agent at once. People keep working.'}
            </p>
            {s.changed_by && (
              <p className="om-hint">
                Last changed by {s.changed_by.id}{s.changed_at ? ` at ${s.changed_at}` : ''}{s.reason ? `: ${s.reason}` : ''}
              </p>
            )}
            {owner ? (
              <>
                <Button variant={s.on ? 'primary' : 'danger'} onClick={() => setConfirm(!s.on)}>
                  {s.on ? 'Resume AI agents' : 'Stop all AI agents'}
                </Button>
                {s.on && deliveryPending && <Button onClick={() => change(true)}>Retry Stop</Button>}
              </>
            ) : (
              <p className="om-hint">Only the owner can stop or resume agents.</p>
            )}
          </>
        )}
      </Load>
      <Dialog
        role="alertdialog"
        open={confirm !== undefined}
        onClose={() => setConfirm(undefined)}
        title={confirm ? 'Stop all AI agents?' : 'Resume AI agents?'}
        description={confirm ? 'Every AI agent is blocked until you approve a resume request.' : 'This files a request in Approvals. Resuming requires a proven passkey.'}
        actions={
          <>
            <Button variant="ghost" onClick={() => setConfirm(undefined)}>Cancel</Button>
            <Button variant={confirm ? 'danger' : 'primary'} onClick={() => change(!!confirm)}>{confirm ? 'Stop agents' : 'Request resume'}</Button>
          </>
        }
      >
        <TextField id="kill-switch-reason" label="Reason (for the audit record)" value={reason} onChange={setReason} />
      </Dialog>
    </Card>
  );
}

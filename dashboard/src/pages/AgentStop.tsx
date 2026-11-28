// SPDX-License-Identifier: Apache-2.0
// Settings > Agents: the agent kill switch (CORE-SEC-6, #159), GET/PUT /v1/agents/kill-switch.
// Everyone signed in sees whether AI agents are stopped; only the owner gets the button. The
// gateway is the boundary (it refuses anyone else, and refuses every agent while the switch is
// on); the page only avoids offering what would be refused.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { Load, TextField, useRun } from './parts';

type KillSwitch = components['schemas']['KillSwitch'];
const PATH = '/v1/agents/kill-switch';

async function call(sdk: OneMind, method: 'GET' | 'PUT', body?: components['schemas']['KillSwitchBody']): Promise<KillSwitch> {
  try {
    const v = await sdk.call<KillSwitch>({ method, path: PATH, body });
    if (!v || typeof v.on !== 'boolean') throw new Error('The hub returned an invalid kill switch state.');
    return v;
  } catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

export function AgentStop() {
  const { token, mock } = useSignedIn();
  const { role } = useShell(); // a real hub's session has no principal; the role comes from GET /v1/me
  if (mock) return null; // demo mode has no gateway to stop agents on
  return <LiveAgentStop token={token} owner={role === 'owner'} roleKnown={role !== undefined} />;
}

function LiveAgentStop({ token, owner, roleKnown }: { token: string; owner: boolean; roleKnown: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const state = usePoll(() => call(sdk, 'GET'), 15_000);
  const run = useRun();
  const [confirm, setConfirm] = useState<boolean>();
  const [reason, setReason] = useState('');
  const change = (on: boolean) =>
    void run(async () => {
      await call(sdk, 'PUT', { on, ...(reason.trim() ? { reason: reason.trim() } : {}) });
      setConfirm(undefined);
      setReason('');
      await state.reload();
    }, on ? 'Stop all AI agents' : 'Resume AI agents');

  return (
    <Card title="Agent kill switch" as="article">
      <Load res={state} what="Loading the agent kill switch">
        {(s) => (
          <>
            <p>
              {s.on ? <StatusPill tone="bad" label="All agents stopped" /> : <StatusPill tone="ok" label="Agents running" />}{' '}
              {s.on
                ? 'The hub refuses every request from an AI agent, and nothing an agent asked for can be approved, until the owner resumes them.'
                : 'Stopping refuses every AI agent at once. People keep working; it is undone with one click.'}
            </p>
            {s.changed_by && (
              <p className="om-hint">
                Last changed by {s.changed_by.id}{s.changed_at ? ` at ${s.changed_at}` : ''}{s.reason ? `: ${s.reason}` : ''}
              </p>
            )}
            {owner ? (
              <Button variant={s.on ? 'primary' : 'danger'} onClick={() => setConfirm(!s.on)}>
                {s.on ? 'Resume AI agents' : 'Stop all AI agents'}
              </Button>
            ) : (
              roleKnown ? <p className="om-hint">Only the owner can stop or resume agents.</p> : null
            )}
          </>
        )}
      </Load>
      <Dialog
        role="alertdialog"
        open={confirm !== undefined}
        onClose={() => setConfirm(undefined)}
        title={confirm ? 'Stop all AI agents?' : 'Resume AI agents?'}
        description={confirm ? 'Every AI agent is refused until you resume them. This is written to the audit record.' : 'AI agents can ask again; anything they ask still waits for your approval. This is written to the audit record.'}
        actions={
          <>
            <Button variant="ghost" onClick={() => setConfirm(undefined)}>Cancel</Button>
            <Button variant={confirm ? 'danger' : 'primary'} onClick={() => change(!!confirm)}>{confirm ? 'Stop agents' : 'Resume agents'}</Button>
          </>
        }
      >
        <TextField id="kill-switch-reason" label="Reason (for the audit record)" value={reason} onChange={setReason} />
      </Dialog>
    </Card>
  );
}

// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions > Never (design §3.6 "Deny rules", §3.5.2 step 3): a requester may never have
// one kind of request (or a whole risk tier) approved without you, whatever a rule or mode says.
// GET/POST /v1/approval-denies, DELETE /v1/approval-denies/{id}.
// Adding one only tightens: the owner, or the person who owns that agent, with no passkey.
// The owner can request approval to remove one after confirming the request in this screen.
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Button, Card, Dialog } from '@onemind/ui';
import type { Action, components } from '@onemind/sdk';
import { usePoll } from '../../lib/hooks';
import { useShell } from '../../shell/Shell';
import { href } from '../../shell/routes';
import { agentKey, explain, isApprovalRequest, read, usePermSdk, useStepUp } from '../../lib/permissions';
import { Load } from '../parts';

type Deny = components['schemas']['ApprovalDeny'];
type AgentView = components['schemas']['AgentView'];

export const TIERS: Record<string, string> = {
  T0: 'Reading things (T0)',
  T1: 'Writing or changing things (T1)',
  T2: 'Sensitive changes such as installs (T2)',
  T3: 'Deleting things (T3)',
  T4: 'Controlling devices (T4)',
  P: 'Anything physical (P)',
};
const short = (name: string) => name.replace(/^(agent|person|plugin|automation):/, '');
const whatOf = (d: Deny) => d.action_type ?? TIERS[d.tier ?? ''] ?? d.tier ?? '';

export function Never() {
  const sdk = usePermSdk();
  const stepUp = useStepUp();
  const isOwner = useShell().role === 'owner';
  const data = usePoll(async () => {
    const [denies, agents, actions] = await Promise.all([
      read(sdk.call<Deny[]>({ method: 'GET', path: '/v1/approval-denies' })),
      sdk.call<AgentView[]>({ method: 'GET', path: '/v1/agents' }).catch(() => [] as AgentView[]),
      sdk.actions.list().catch(() => []),
    ]);
    return { denies, agents: agents.map((a) => agentKey(a.id)), types: [...new Set(actions.map((a) => String(a.type)))].sort() };
  }, 0);
  const [who, setWho] = useState('');
  const [by, setBy] = useState<'type' | 'tier'>('tier');
  const [type, setType] = useState('');
  const [tier, setTier] = useState('T3');
  const [reason, setReason] = useState('');
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string; pending?: string }>();
  const [removing, setRemoving] = useState<{ deny: Deny; busy?: boolean; error?: string }>();

  const done = async (job: () => Promise<unknown>, ok: string): Promise<boolean> => {
    let worked = false;
    try {
      await job();
      setNote({ tone: 'ok', text: ok });
      worked = true;
    } catch (e) {
      setNote({ tone: 'bad', text: explain(e) });
    }
    await data.reload();
    return worked;
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    const body = { principal: who.trim(), ...(by === 'type' ? { action_type: type.trim() } : { tier }), ...(reason.trim() ? { reason: reason.trim() } : {}) };
    if (await done(() => read(sdk.call<Deny>({ method: 'POST', path: '/v1/approval-denies', body })), `Added. ${short(body.principal)} can no longer have that approved without you.`)) {
      setWho(''); // a second press must not send the same rule again
      setType('');
      setReason('');
    }
  };
  const remove = async () => {
    if (!removing) return;
    const d = removing.deny;
    setRemoving({ deny: d, busy: true });
    try {
      const result = await stepUp((c) => c.call<void | Action>({ method: 'DELETE', path: `/v1/approval-denies/${encodeURIComponent(d.id)}` }), sdk);
      setNote(isApprovalRequest(result)
        ? { tone: 'ok', text: `Removal requested for ${short(d.principal)}.`, pending: result.id }
        : { tone: 'ok', text: `Removed the rule for ${short(d.principal)}.` });
    } catch (e) {
      setRemoving({ deny: d, error: explain(e) });
      return;
    }
    setRemoving(undefined);
    await data.reload();
  };

  return (
    <Load res={data} what="Loading never rules">
      {({ denies, agents, types }) => (
        <>
          {note && <p className={`om-note om-tone-${note.tone}`} role={note.tone === 'bad' ? 'alert' : 'status'}>{note.text}{note.pending && <> <Link to={href.approval(note.pending)}>Review in Approvals</Link>.</>}</p>}
          <Card title={`Never without you (${denies.length})`} subtitle="These win over every rule and mode: a request they cover always waits for a person. Removing one needs the owner’s approval.">
            {denies.length === 0 ? <p className="om-hint">No never rules yet.</p> : (
              <ul className="dash-list" aria-label="Never rules">
                {denies.map((d) => {
                  const what = whatOf(d);
                  return (
                    <li key={d.id} className="dash-actions">
                      <span><strong>{short(d.principal)}</strong> may never: {what}{d.reason ? <span className="om-hint"> · {d.reason}</span> : null}</span>
                      {isOwner && <Button size="sm" variant="secondary" aria-label={`Remove: ${short(d.principal)} may never ${what}`} onClick={() => setRemoving({ deny: d })}>Remove</Button>}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <Card title="Add a never rule" subtitle="Adding one only makes things safer, so it needs no passkey.">
            <form onSubmit={(e) => void add(e)} className="dash-stack">
              <label>Who
                <input list="never-who" required value={who} placeholder="agent:notes-helper" onChange={(e) => setWho(e.target.value)} />
              </label>
              <datalist id="never-who">{agents.map((a) => <option key={a} value={a} />)}</datalist>
              <fieldset>
                <legend>May never have approved</legend>
                <label><input type="radio" name="never-by" checked={by === 'tier'} onChange={() => setBy('tier')} /> A whole kind of request</label>
                <label><input type="radio" name="never-by" checked={by === 'type'} onChange={() => setBy('type')} /> One request type</label>
              </fieldset>
              {by === 'tier' ? (
                <label>Kind of request
                  <select value={tier} onChange={(e) => setTier(e.target.value)}>
                    {Object.entries(TIERS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
              ) : (
                <>
                  <label>Request type <input list="never-types" required value={type} placeholder="app.install" pattern="[a-z][a-z0-9_]*(\.[a-z0-9_]+)+" onChange={(e) => setType(e.target.value)} /></label>
                  <datalist id="never-types">{types.map((t) => <option key={t} value={t} />)}</datalist>
                </>
              )}
              <label>Why (optional) <input value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} /></label>
              <div><Button type="submit" variant="primary">Add never rule</Button></div>
            </form>
          </Card>
          {removing && (
            <Dialog
              open
              role="alertdialog"
              title={`Allow ${short(removing.deny.principal)} to have ${whatOf(removing.deny)} approved again?`}
              description="After approval, rules and modes can answer these requests for you."
              onClose={() => (removing.busy ? undefined : setRemoving(undefined))}
              actions={<>
                <Button onClick={() => setRemoving(undefined)} disabled={removing.busy}>Cancel</Button>
                <Button variant="primary" busy={removing.busy} onClick={() => void remove()}>Request removal</Button>
              </>}
            >
              {removing.error && <p className="om-note om-tone-bad" role="alert">{removing.error}</p>}
            </Dialog>
          )}
        </>
      )}
    </Load>
  );
}

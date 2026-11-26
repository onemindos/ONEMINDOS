// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions > Never (design §3.6 "Deny rules", §3.5.2 step 3): a requester may never have
// one kind of request (or a whole risk tier) approved without you, whatever a rule or mode says.
// GET/POST /v1/approval-denies, DELETE /v1/approval-denies/{id}.
// Adding one only tightens: the owner, or the person who owns that agent, with no passkey.
// Removing one loosens: the owner only, and the gateway asks for a fresh passkey.
import { useState, type FormEvent } from 'react';
import { Button, Card } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import { usePoll } from '../../lib/hooks';
import { agentKey, explain, read, usePermSdk, useStepUp } from '../../lib/permissions';
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
const PATH = '/v1/approval-denies';
const short = (name: string) => name.replace(/^(agent|person|plugin|automation):/, '');

export function Never() {
  const sdk = usePermSdk();
  const stepUp = useStepUp();
  const data = usePoll(async () => {
    const [denies, agents, actions] = await Promise.all([
      read(sdk.call<Deny[]>({ method: 'GET', path: PATH })),
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
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string }>();

  const done = async (job: () => Promise<unknown>, ok: string) => {
    try {
      await job();
      setNote({ tone: 'ok', text: ok });
    } catch (e) {
      setNote({ tone: 'bad', text: explain(e) });
    }
    await data.reload();
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    const body = { principal: who.trim(), ...(by === 'type' ? { action_type: type.trim() } : { tier }), ...(reason.trim() ? { reason: reason.trim() } : {}) };
    void done(() => read(sdk.call<Deny>({ method: 'POST', path: PATH, body })), `Added. ${short(body.principal)} can no longer have that approved without you.`);
  };
  const remove = (d: Deny) => done(
    () => stepUp((c) => c.call<void>({ method: 'DELETE', path: `${PATH}/${encodeURIComponent(d.id)}` }), sdk),
    `Removed the rule for ${short(d.principal)}.`,
  );

  return (
    <Load res={data} what="Loading never rules">
      {({ denies, agents, types }) => (
        <>
          {note && <p className={`om-note om-tone-${note.tone}`} role={note.tone === 'bad' ? 'alert' : 'status'}>{note.text}</p>}
          <Card title={`Never without you (${denies.length})`} subtitle="These win over every rule and mode: a request they cover always waits for a person. Removing one asks for the owner’s passkey.">
            {denies.length === 0 ? <p className="om-hint">No never rules yet.</p> : (
              <ul className="dash-list" aria-label="Never rules">
                {denies.map((d) => {
                  const what = d.action_type ?? TIERS[d.tier ?? ''] ?? d.tier ?? '';
                  return (
                    <li key={d.id} className="dash-actions">
                      <span><strong>{short(d.principal)}</strong> may never: {what}{d.reason ? <span className="om-hint"> · {d.reason}</span> : null}</span>
                      <Button size="sm" variant="secondary" aria-label={`Remove: ${short(d.principal)} may never ${what}`} onClick={() => void remove(d)}>Remove</Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <Card title="Add a never rule" subtitle="Adding one only makes things safer, so it needs no passkey.">
            <form onSubmit={add} className="dash-stack">
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
        </>
      )}
    </Load>
  );
}

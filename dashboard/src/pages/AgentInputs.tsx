// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Button, Card } from '@onemind/ui';
import type { Action, components } from '@onemind/sdk';
import { usePoll } from '../lib/hooks';
import { explain, isApprovalRequest, read, usePermSdk, useStepUp } from '../lib/permissions';
import { href } from '../shell/routes';
import { Load } from './parts';

type Inputs = components['schemas']['AgentInputsView'];
type InputBody = components['schemas']['AgentInputsBody'];
type Agent = components['schemas']['AgentView'];
const SOURCES = { web: 'Web pages', email: 'Email', files: 'Files', chat: 'External chats' } as const;
const kinds = Object.keys(SOURCES) as Array<keyof typeof SOURCES>;

export function AgentInputs() {
  const sdk = usePermSdk();
  const agents = usePoll(() => read(sdk.call<Agent[]>({ method: 'GET', path: '/v1/agents' })), 0);
  const [selected, select] = useState('');
  return <Card title="Outside text access">
    <Load res={agents} what="Loading agents">
      {(rows) => rows.length === 0 ? <p>No agents are registered.</p> : <>
        <label>Agent <select value={selected} onChange={(e) => select(e.target.value)}>
          <option value="">Choose an agent</option>
          {rows.map((agent) => <option key={agent.id} value={agent.id}>{agent.id}</option>)}
        </select></label>
        {selected && <AgentInputsEditor key={selected} name={selected} />}
      </>}
    </Load>
  </Card>;
}

function AgentInputsEditor({ name }: { name: string }) {
  const sdk = usePermSdk();
  const stepUp = useStepUp();
  const current = usePoll(() => read(sdk.call<Inputs>({ method: 'GET', path: `/v1/agents/${encodeURIComponent(name)}/inputs` })), 0);
  const [draft, setDraft] = useState<InputBody>();
  const [risk, setRisk] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; pending?: string; error?: boolean }>();

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft || saving) return;
    setSaving(true);
    setMessage(undefined);
    try {
      const body: InputBody = { ...draft, accept_injection_risk: risk.split(',').map((v) => v.trim()).filter(Boolean) };
      const result = await stepUp((client) => client.call<Inputs | Action>({
        method: 'PUT', path: `/v1/agents/${encodeURIComponent(name)}/inputs`, body,
      }), sdk);
      setMessage(isApprovalRequest(result) ? { text: 'Input change requested.', pending: result.id } : { text: 'Inputs saved.' });
      setDraft(undefined);
      await current.reload();
    } catch (error) {
      setMessage({ text: explain(error), error: true });
    } finally {
      setSaving(false);
    }
  }

  return <Load res={current} what="Loading the agent’s inputs">
    {(inputs) => <>
      <p>{inputs.external_inputs.length ? `Reads outside text: ${inputs.external_inputs.join(', ')}.` : 'No outside text declared.'}
        {!inputs.declared && ' This is the default until you save a declaration.'}</p>
      {message && <p role={message.error ? 'alert' : 'status'}>{message.text}
        {message.pending && <> <Link to={href.approval(message.pending)}>Review in Approvals</Link>.</>}
      </p>}
      {draft ? <form className="dash-stack" onSubmit={(e) => void save(e)}>
        <fieldset disabled={saving}>
          <legend>Sources the agent reads outside OneMind</legend>
          {kinds.map((kind) => <label key={kind}>
            <input type="checkbox" checked={draft.external_inputs.includes(kind)} onChange={(e) => {
              const external_inputs = e.target.checked
                ? [...draft.external_inputs, kind] : draft.external_inputs.filter((value) => value !== kind);
              setDraft({ ...draft, external_inputs });
            }} /> {SOURCES[kind]}
          </label>)}
        </fieldset>
        <label>Accepted injection risk (comma-separated action types)
          <input value={risk} disabled={saving} onChange={(e) => setRisk(e.target.value)} />
        </label>
        <div className="dash-actions">
          <Button type="submit" disabled={saving}>Save inputs</Button>
          <Button type="button" disabled={saving} onClick={() => setDraft(undefined)}>Cancel</Button>
        </div>
      </form> : <Button onClick={() => {
        setMessage(undefined);
        setDraft({ external_inputs: kinds.filter((kind) => inputs.external_inputs.includes(kind)) });
        setRisk(inputs.accept_injection_risk.join(', '));
      }}>Edit inputs</Button>}
    </>}
  </Load>;
}

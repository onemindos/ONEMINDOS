// SPDX-License-Identifier: Apache-2.0
// Owner writer screens for Settings > Permissions (D-028; gateway permissions design 3.11; issue #1214):
// who can open an app (apps.access.set) and what an agent reads outside OneMind (agents.inputs.set).
// Both are owner changes on routes the hub guards with a step-up: a change that adds power (sharing with
// more people, an agent declared to read less) answers 401 step_up_required, and the SDK's shared helper
// (useGateway: completeStepUp) asks for a key at the level the verification table sets (L2 by default)
// and, before the box's first proven key, for the code on the box's own screen (lib/boxcode.tsx), then
// sends the same change once more. A change that only takes power away goes through at once. The hub
// decides which is which; nothing here invents a check.
// The CLI has the same settings: `onemind apps access get|set` and `onemind agents inputs get|set`.
import { useState } from 'react';
import type { components } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { sessionLapsed, useGateway, viaSdk } from '../lib/gateway';
import { useSignedIn } from '../session';
import { keyErrorText } from '../lib/keyErrors';
import { Load } from './parts';

type Access = components['schemas']['AppAccess'];
type Inputs = components['schemas']['AgentInputsView'];
type InputKind = components['schemas']['AgentInputsBody']['external_inputs'][number];
type UserInfo = components['schemas']['UserInfo'];

/** Roles that sharing decides for. Owners and adults open every app whatever the sharing says. */
export const SHARED_ROLES = [['teen', 'Teens'], ['child', 'Children'], ['guest', 'Guests']] as const;
const ALWAYS = new Set(['owner', 'adult']);
const INPUTS: [InputKind, string][] = [
  ['web', 'Web pages'], ['email', 'Email'], ['files', 'Files it opens itself'], ['chat', 'Many chats on one token (a chat host)'],
];
const STEP_UP_HINT = 'Adding people, moving an app to its own sign-in, or loosening an agent, asks for your proven key. Before your first proven key it asks for any passkey plus the code on the box’s own screen. Taking access away happens at once.';

type Person = { id: string; name: string; role: string };
type Note = { tone: 'ok' | 'bad'; text: string };
/** The people this screen can share with (GET /v1/users, generated UserInfo type): disabled accounts left out. */
export function people(users: UserInfo[]): Person[] {
  return users.filter((u) => !u.disabled).map((u) => ({ id: u.id, name: u.display_name || u.username || u.id, role: u.role }));
}

/** A save the hub refused because the sign-in lapsed signs out, as every read does (usePoll); the form then
 *  shows no note. A 401 that names a reason (a step-up the hub wants) is the form's to explain. */
function guarded<T>(signOut: () => void, run: () => Promise<T>): Promise<T> {
  return run().catch((e: unknown) => { if (sessionLapsed(e)) signOut(); throw e; });
}

const toggle = (list: string[], v: string, on: boolean) => (on ? [...new Set([...list, v])] : list.filter((x) => x !== v));
const same = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join('\0') === [...b].sort().join('\0');

export function AppSharingEditor({ appId, appName }: { appId: string; appName: string }) {
  const { token, signOut } = useSignedIn();
  const client = useGateway(token);
  const path = `/v1/apps/${encodeURIComponent(appId)}/access`;
  const access = usePoll(() => viaSdk(() => client.call<Access>({ method: 'GET', path })), 0);
  const users = usePoll(() => viaSdk(() => client.call<UserInfo[]>({ method: 'GET', path: '/v1/users' })).then(people), 0);
  const [note, setNote] = useState<Note>();
  return <Card title={`Who can open ${appName}`} subtitle="Owners and adults can always open every app. Choose who else can.">
    <Load res={access} what="Loading sharing">
      {(a) => <SharingForm key={`${a.roles.join()}|${a.people.map((p) => p.id).join()}|${a.auth}`} access={a} users={users.data ?? (users.error ? null : undefined)}
        onNote={setNote} save={(body) => guarded(signOut, () => viaSdk(() => client.call<Access>({ method: 'PUT', path, body }))).then(() => { void access.reload(); })} />}
    </Load>
    {note && <p role="status" className={`om-note om-tone-${note.tone}`}>{note.text}</p>}
  </Card>;
}

function SharingForm({ access, users, save, onNote: setNote }: { access: Access; users?: Person[] | null; onNote: (n?: Note) => void; save: (b: { roles: string[]; people: string[]; auth: string }) => Promise<void> }) {
  const [roles, setRoles] = useState(access.roles);
  const [chosen, setChosen] = useState(access.people.map((p) => p.id));
  const [auth, setAuth] = useState<string>(access.auth);
  const [busy, setBusy] = useState(false);
  const changed = !same(roles, access.roles) || !same(chosen, access.people.map((p) => p.id)) || auth !== access.auth;
  // People who need sharing to open it (owners and adults always can); anyone already shared stays listed.
  const pickable = (users ?? []).filter((u) => !ALWAYS.has(u.role) || chosen.includes(u.id));
  const go = async () => {
    setBusy(true); setNote(undefined);
    try {
      await save({ roles, people: chosen, auth });
      setNote({ tone: 'ok', text: 'Saved.' });
    } catch (e) { if (!sessionLapsed(e)) setNote({ tone: 'bad', text: `Sharing was not changed: ${keyErrorText(e)}` }); } finally { setBusy(false); }
  };
  return <>
    <fieldset><legend>Everyone with this role</legend>
      {SHARED_ROLES.map(([id, label]) => <label key={id}><input type="checkbox" checked={roles.includes(id)} disabled={busy}
        onChange={(e) => setRoles(toggle(roles, id, e.target.checked))} /> {label}</label>)}
    </fieldset>
    <fieldset><legend>People by name</legend>
      {users === undefined ? <p className="om-hint" role="status">Loading people…</p>
        : users === null ? <p className="om-note om-tone-warn" role="status">Couldn’t load the people on this box, so only roles can be changed now. Reload to try again.</p>
        : pickable.length === 0 ? <p className="om-hint">No teens, children or guests on this box yet. Add people under Users &amp; roles.</p>
        : pickable.map((u) => <label key={u.id}><input type="checkbox" checked={chosen.includes(u.id)} disabled={busy}
          onChange={(e) => setChosen(toggle(chosen, u.id, e.target.checked))} /> {u.name}</label>)}
    </fieldset>
    <fieldset><legend>How people sign in to it</legend>
      <label><input type="radio" name="om-share-auth" checked={auth === 'onemind'} disabled={busy} onChange={() => setAuth('onemind')} /> OneMind sign-in (recommended)</label>
      <label><input type="radio" name="om-share-auth" checked={auth === 'app'} disabled={busy} onChange={() => setAuth('app')} /> The app’s own sign-in</label>
    </fieldset>
    <p className="om-hint">{STEP_UP_HINT}</p>
    <div className="dash-actions"><Button variant="primary" disabled={busy || !changed} onClick={() => void go()}>{busy ? 'Saving…' : 'Save sharing'}</Button></div>
  </>;
}

export function AgentInputsEditor({ agentId }: { agentId: string }) {
  const { token, signOut } = useSignedIn();
  const client = useGateway(token);
  const path = `/v1/agents/${encodeURIComponent(agentId)}/inputs`;
  const inputs = usePoll(() => viaSdk(() => client.call<Inputs>({ method: 'GET', path })), 0);
  const [note, setNote] = useState<Note>();
  return <Card title="What this agent reads outside OneMind" subtitle="An agent that reads web pages, email or files can be steered by what it reads. While it does, no standing approval accepts its requests: you approve each one.">
    <Load res={inputs} what="Loading what this agent reads">
      {(v) => <InputsForm key={`${v.external_inputs.join()}|${v.accept_injection_risk.join()}|${v.declared}`} view={v}
        onNote={setNote} save={(body) => guarded(signOut, () => viaSdk(() => client.call<Inputs>({ method: 'PUT', path, body }))).then(() => { void inputs.reload(); })} />}
    </Load>
    {note && <p role="status" className={`om-note om-tone-${note.tone}`}>{note.text}</p>}
  </Card>;
}

function InputsForm({ view, save, onNote: setNote }: { view: Inputs; onNote: (n?: Note) => void; save: (b: { external_inputs: InputKind[]; accept_injection_risk: string[] }) => Promise<void> }) {
  const known = (view.external_inputs as string[]).filter((x): x is InputKind => INPUTS.some(([k]) => k === x));
  const [reads, setReads] = useState<InputKind[]>(view.declared ? known : INPUTS.map(([k]) => k));
  const [accept, setAccept] = useState(view.accept_injection_risk.join(', '));
  const [busy, setBusy] = useState(false);
  const acceptList = accept.split(',').map((x) => x.trim()).filter(Boolean);
  const changed = !view.declared || !same(reads, known) || !same(acceptList, view.accept_injection_risk);
  const go = async () => {
    setBusy(true); setNote(undefined);
    try {
      await save({ external_inputs: reads, accept_injection_risk: acceptList });
      setNote({ tone: 'ok', text: 'Saved.' });
    } catch (e) { if (!sessionLapsed(e)) setNote({ tone: 'bad', text: `Nothing changed: ${keyErrorText(e)}` }); } finally { setBusy(false); }
  };
  return <>
    <p>{view.permanently_tainted ? 'Now: it reads outside text, so you approve each of its requests.' : 'Now: it reads nothing outside OneMind that the gateway cannot see.'}</p>
    {!view.declared && <p className="om-note om-tone-warn" role="note">You haven’t said what this agent reads yet, so it counts as reading everything below. Untick what it never reads, then save.</p>}
    <fieldset><legend>It reads</legend>
      {INPUTS.map(([id, label]) => <label key={id}><input type="checkbox" checked={reads.includes(id)} disabled={busy}
        onChange={(e) => setReads(toggle(reads, id, e.target.checked) as InputKind[])} /> {label}</label>)}
    </fieldset>
    {reads.length === 0 && <p className="om-hint">Nothing ticked: you are saying it reads nothing outside OneMind. Standing approvals can then accept its requests.</p>}
    <details className="om-details">
      <summary>Accepted injection risk (advanced)</summary>
      <label>Write request types you accept the risk for, comma separated{' '}<input value={accept} disabled={busy} onChange={(e) => setAccept(e.target.value)} placeholder="app.restart" /></label>
      <p className="om-hint">Recorded for later; not in effect yet{view.accept_injection_risk_effective ? '' : ' (the permission engine does not read it yet)'}.</p>
    </details>
    <p className="om-hint">{STEP_UP_HINT}</p>
    <div className="dash-actions"><Button variant="primary" disabled={busy || !changed} onClick={() => void go()}>{busy ? 'Saving…' : 'Save'}</Button></div>
  </>;
}

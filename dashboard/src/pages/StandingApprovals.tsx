// SPDX-License-Identifier: Apache-2.0
// Settings > Standing approvals (contract §12.17; D-028; issue #1214): the owner's "yes, in advance" for a
// narrow kind of request. The hub's hard limits stay the hub's: only read and write requests are covered
// (never sensitive or destructive ones), each one names an agent, automation, plugin or person exactly,
// expires within 90 days and has a daily limit. An agent that reads outside text is never covered.
// Creating one and confirming a paused legacy one add power, so the hub answers 401 step_up_required and
// the SDK's shared helper (useGateway: completeStepUp) asks for the proven key in place, or, before the
// box's first proven key, any passkey plus the code on the box's own screen. Removing one takes power away
// and goes through at once. The CLI has the same: `onemind actions policies list|create|confirm|remove`.
import { useState } from 'react';
import { Link } from 'react-router';
import type { components } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, Table, formatDay } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { sessionLapsed, useGateway, viaSdk } from '../lib/gateway';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { keyErrorText } from './SignInKeys';
import { Load } from './parts';

type Policy = components['schemas']['ApprovalPolicy'];
type Body = components['schemas']['PolicyBody'];
type Note = { tone: 'ok' | 'bad'; text: string };

export const MAX_DAYS = 90;
const list = (s: string) => [...new Set(s.split(',').map((x) => x.trim()).filter(Boolean))];

/** The request body for a new standing approval, or the plain reason it can't be one yet. */
export function buildPolicy(f: { name: string; types: string; from: string; perDay: string; days: string; window: string; params: string }, now: number): Body | string {
  const types = list(f.types);
  const from = list(f.from);
  const perDay = Number(f.perDay);
  const days = Number(f.days);
  if (!types.length) return 'Say which kind of request it covers, for example app.restart.';
  if (!from.length) return 'Say who may ask, for example agent:hermes.';
  if (from.some((r) => r.endsWith(':*'))) return 'Name each agent or automation exactly; "everyone" is not allowed.';
  if (!Number.isInteger(perDay) || perDay < 1 || perDay > 1000) return 'The daily limit is a whole number from 1 to 1000.';
  if (!Number.isInteger(days) || days < 1 || days > MAX_DAYS) return `It ends after 1 to ${MAX_DAYS} days.`;
  let params: Record<string, Record<string, unknown>> = {};
  if (f.params.trim()) {
    try {
      const p: unknown = JSON.parse(f.params);
      if (!p || typeof p !== 'object' || Array.isArray(p)) return 'Limits on values must be a JSON object, for example {"app_id": {"enum": ["notes"]}}.';
      params = p as typeof params;
    } catch { return 'Limits on values are not valid JSON.'; }
  }
  return {
    ...(f.name.trim() ? { name: f.name.trim() } : {}),
    allow: { types, requested_by: from, params },
    limits: { per_day: perDay },
    ...(f.window ? { window_id: f.window } : {}),
    expires_at: new Date(now + days * 86_400_000).toISOString(),
  };
}

export function StandingApprovals() {
  // The role comes from the shell, as on every other owner-only screen (SettingsSecurity, Care): a real
  // gateway session carries no principal, so the shell reads GET /v1/me (roleOf). Core still refuses a
  // non-owner on every route this page calls.
  const { role } = useShell();
  const { token, mock, signOut } = useSignedIn();
  const notice = (text: string) => <><PageHeader title="Standing approvals" /><Card title="Standing approvals"><p role="status">{text}</p></Card></>;
  if (mock) return notice('Connect to a real hub to see its standing approvals. Demo mode has none.');
  if (role === undefined) return notice('Checking who is signed in…');
  if (role !== 'owner') return notice('Only an owner can see and change standing approvals.');
  return <Live token={token} signOut={signOut} />;
}

type Pick_ = { id: string; label: string };
function picks(raw: unknown, label: (r: Record<string, unknown>) => string | undefined): Pick_[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((x) => {
    const r = (x && typeof x === 'object' ? x : {}) as Record<string, unknown>;
    return typeof r.id === 'string' ? [{ id: r.id, label: label(r) ?? r.id }] : [];
  });
}

function Live({ token, signOut }: { token: string; signOut: () => void }) {
  const client = useGateway(token);
  const policies = usePoll(() => viaSdk(() => client.call<Policy[]>({ method: 'GET', path: '/v1/approval-policies' })), 0);
  // Suggestions from real data: the agents and automations on this box, and its maintenance windows.
  // A standing approval names a requester as <kind>:<id>; an agent id without its kind gets agent: in front.
  // /v1/agents has a generated schema (AgentView); the rules and windows routes have none yet, so picks() reads them.
  const agents = usePoll(() => viaSdk(() => client.call<components['schemas']['AgentView'][]>({ method: 'GET', path: '/v1/agents' }))
    .then((r) => r.map((a) => ({ id: a.id.includes(':') ? a.id : `agent:${a.id}`, label: a.id }))), 0);
  const rules = usePoll(() => viaSdk(() => client.call<unknown>({ method: 'GET', path: '/v1/automation/rules' }))
    .then((r) => picks(r, (x) => (typeof x.name === 'string' ? x.name : undefined)).map((p) => ({ id: `automation:${p.id}`, label: p.label }))), 0);
  const windows = usePoll(() => viaSdk(() => client.call<unknown>({ method: 'GET', path: '/v1/windows' })).then((r) => picks(r, (x) => (typeof x.name === 'string' ? x.name : undefined))), 0);
  const [note, setNote] = useState<Note>();
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<string>();
  const now = client.hubNow();
  const windowName = (id: string | null | undefined) => (id ? windows.data?.find((w) => w.id === id)?.label ?? id : 'Any time');

  const run = async (job: () => Promise<unknown>, ok: string, what: string) => {
    setBusy(true); setNote(undefined);
    try { await job(); setNote({ tone: 'ok', text: ok }); return true; } catch (e) {
      // A lapsed sign-in signs out, as every read does; a check the hub names is explained in plain words.
      if (sessionLapsed(e)) { signOut(); return false; }
      setNote({ tone: 'bad', text: `${what}: ${keyErrorText(e)}` }); return false;
    } finally { setBusy(false); setRemoving(undefined); void policies.reload(); }
  };
  const confirm = (p: Policy) => run(() => viaSdk(() => client.call({ method: 'POST', path: `/v1/approval-policies/${encodeURIComponent(p.id)}/confirm` })),
    `${p.name ?? p.id} is on again.`, `Turning ${p.name ?? p.id} back on`);
  const remove = (p: Policy) => run(() => viaSdk(() => client.call({ method: 'DELETE', path: `/v1/approval-policies/${encodeURIComponent(p.id)}` })),
    `${p.name ?? p.id} removed. Its requests wait for you again.`, `Removing ${p.name ?? p.id}`);
  const create = (body: Body) => run(() => viaSdk(() => client.call({ method: 'POST', path: '/v1/approval-policies', body })),
    'Standing approval created.', 'Creating the standing approval');

  return <div className="dash-stack">
    <PageHeader title="Standing approvals" lede="Say yes in advance to a narrow kind of request, so it doesn't wait for you each time. Everything else still waits in Approvals." />
    <Card title="What a standing approval can cover">
      <ul>
        <li>Only read and write requests. Sensitive and destructive ones (installing, removing data, restoring) always wait for you.</li>
        <li>Only the agent, automation, plugin or person it names, never "everyone".</li>
        <li>Up to a daily limit, and it always ends, within {MAX_DAYS} days.</li>
        <li>Never an agent that reads web pages, email or files: see <Link to="/settings/permissions">Permissions &gt; By agent</Link>.</li>
      </ul>
      <p className="om-hint">Creating one, or turning a paused one back on, asks for your proven key. Before your first proven key it asks for any passkey plus the code on the box’s own screen.</p>
    </Card>
    <Card title="Your standing approvals">
      <Load res={policies} what="Loading standing approvals">
        {(rows) => rows.length === 0 ? <p className="om-hint">None yet. Every request waits for you in Approvals.</p> : <Table
          caption="Standing approvals" hideCaption rows={rows} rowKey={(p) => p.id}
          columns={[
            { key: 'name', header: 'Name', render: (p) => <><strong>{p.name ?? p.id}</strong><p className="om-hint">Covers {p.allow.types.join(', ')}</p>
              <p className="om-hint">{p.state === 'expired' ? 'Ended' : 'Ends'} {formatDay(p.expires_at)} · {windowName(p.window_id)}</p></> },
            { key: 'from', header: 'Who may ask', render: (p) => p.allow.requested_by.join(', ') },
            { key: 'limit', header: 'Today', render: (p) => `${p.uses_24h} of ${p.limits.per_day}` },
            { key: 'window', header: 'Only during', render: (p) => windowName(p.window_id), secondary: true },
            { key: 'ends', header: 'Ends', render: (p) => formatDay(p.expires_at) },
            { key: 'state', header: 'State', render: (p) => <StatusPill tone={p.state === 'active' ? 'ok' : p.state === 'paused' ? 'warn' : 'neutral'}
              label={p.state === 'active' ? 'On' : p.state === 'paused' ? 'Paused: confirm it' : 'Ended'} /> },
            { key: 'x', header: 'Actions', render: (p) => <span className="dash-actions">
              {p.state === 'paused' && <Button size="sm" disabled={busy} aria-label={`Turn ${p.name ?? p.id} back on`} onClick={() => void confirm(p)}>Turn back on</Button>}
              {removing === p.id
                ? <><Button size="sm" variant="danger" disabled={busy} aria-label={`Confirm remove ${p.name ?? p.id}`} onClick={() => void remove(p)}>Confirm remove</Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => setRemoving(undefined)}>Keep it</Button></>
                : <Button size="sm" variant="ghost" disabled={busy} aria-label={`Remove ${p.name ?? p.id}`} onClick={() => setRemoving(p.id)}>Remove</Button>}
            </span> },
          ]} />}
      </Load>
      {policies.data?.some((p) => p.state === 'paused') && <p className="om-hint">Paused ones were made before names had to be exact. Turn one back on only if it still names who you mean.</p>}
    </Card>
    <NewPolicy busy={busy} now={now} who={[...(agents.data ?? []), ...(rules.data ?? [])]} windows={windows.data ?? []}
      missing={{ who: !!(agents.error || rules.error), windows: !!windows.error }} onCreate={create} onInvalid={(text) => setNote({ tone: 'bad', text })} />
    {note && <p role="status" className={`om-note om-tone-${note.tone}`}>{note.text}</p>}
  </div>;
}

const EMPTY = { name: '', types: '', from: '', perDay: '3', days: '30', window: '', params: '' };

function NewPolicy({ busy, now, who, windows, missing, onCreate, onInvalid }: {
  busy: boolean; now: number; who: Pick_[]; windows: Pick_[]; missing: { who: boolean; windows: boolean };
  onCreate: (b: Body) => Promise<boolean>; onInvalid: (text: string) => void;
}) {
  const [f, setF] = useState(EMPTY);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    const body = buildPolicy(f, now);
    if (typeof body === 'string') { onInvalid(body); return; }
    if (await onCreate(body)) setF(EMPTY);
  };
  return <Card title="New standing approval">
    <div className="dash-stack">
      <label>Name (optional){' '}<input value={f.name} maxLength={120} onChange={set('name')} placeholder="Nightly restarts" /></label>
      <label>Kinds of request it covers, comma separated{' '}<input value={f.types} onChange={set('types')} placeholder="app.restart" /></label>
      <label>Who may ask, comma separated{' '}<input value={f.from} list="om-policy-who" onChange={set('from')} placeholder="agent:hermes" /></label>
      <datalist id="om-policy-who">{who.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}</datalist>
      {missing.who && <p className="om-note om-tone-warn" role="status">Couldn’t load the agents and automations on this box, so there are no suggestions. Type the name exactly, for example agent:hermes, or reload to try again.</p>}
      <label>At most this many a day{' '}<input type="number" min={1} max={1000} value={f.perDay} onChange={set('perDay')} /></label>
      <label>Ends after (days){' '}<input type="number" min={1} max={MAX_DAYS} value={f.days} onChange={set('days')} /></label>
      <label>Only during{' '}<select value={f.window} onChange={set('window')}>
        <option value="">Any time</option>
        {windows.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
      </select></label>
      {missing.windows && <p className="om-note om-tone-warn" role="status">Couldn’t load the maintenance windows, so only “Any time” is offered. An app update needs a window, so reload before you make one for app.update.</p>}
      <details className="om-details">
        <summary>Limit to certain values (advanced)</summary>
        <label>JSON, for example {'{"app_id": {"enum": ["notes"]}}'}{' '}<textarea rows={3} value={f.params} onChange={set('params')} /></label>
      </details>
      <div className="dash-actions"><Button variant="primary" disabled={busy} onClick={() => void submit()}>Create standing approval</Button></div>
    </div>
  </Card>;
}

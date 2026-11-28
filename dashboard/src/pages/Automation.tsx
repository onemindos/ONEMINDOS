// SPDX-License-Identifier: Apache-2.0
// Read-only view of the gateway's automation engine (/v1/automation): the kill switch, the rules,
// their schedules and what they did last. Creating, enabling and pausing are approvals-bound or
// owner actions and come in a follow-up; this page cannot change a rule. (#141, UMB-P04.)
import { useMemo } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load } from './parts';
import { Windows } from './automation/Windows';

type Rec = Record<string, unknown>;
function record(value: unknown): Rec {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The hub returned an invalid automation record.');
  return value as Rec;
}
function records(value: unknown): Rec[] {
  if (!Array.isArray(value)) throw new Error('The hub returned an invalid automation list.');
  return value.map(record);
}
function text(value: unknown, missing = 'Not reported') { return typeof value === 'string' && value ? value : missing; }
function describeTrigger(trigger: unknown): string {
  const t = trigger && typeof trigger === 'object' && !Array.isArray(trigger) ? (trigger as Rec) : {};
  const sched = t.schedule && typeof t.schedule === 'object' ? (t.schedule as Rec) : undefined;
  if (sched) return `On a schedule (${text(sched.cron)}, ${text(sched.tz)})`;
  if (t.event !== undefined) return 'When an event happens';
  return 'Unknown trigger';
}
async function read(client: OneMind, path: string) {
  try { return await client.call<unknown>({ method: 'GET', path }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

export function Automation() {
  const { token, person, mock } = useSignedIn();
  return mock ? <><PageHeader title="Automation" /><p role="status">Connect to a real hub to view automation rules. Demo mode has no automation data.</p></> : <LiveAutomation key={person} token={token} />;
}

function LiveAutomation({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const state = usePoll(async () => record(await read(client, '/v1/automation/state')), 30_000);
  const rules = usePoll(async () => records(await read(client, '/v1/automation/rules')), 30_000);
  const schedules = usePoll(async () => records(await read(client, '/v1/automation/schedules')), 30_000);
  const runs = usePoll(async () => records(await read(client, '/v1/automation/runs?limit=20')), 30_000);
  const all = [state, rules, schedules, runs];
  const nextFire = (id: unknown) => {
    const s = schedules.data?.find((x) => x.rule_id === id);
    return s ? text(s.next_fire_at, 'Not scheduled') : undefined;
  };
  const ruleName = (id: unknown) => text(rules.data?.find((r) => r.id === id)?.name, text(id));
  return <div className="dash-stack">
    <PageHeader title="Automation" lede="Rules your hub runs on a schedule or when something happens. This page only reads rules; it cannot create, change or pause one. Maintenance windows below can be edited by an owner." />
    <Button onClick={() => all.forEach((r) => void r.reload())}>Refresh automation</Button>
    {all.some((r) => r.error && r.data !== undefined) && <p role="status">Could not refresh. Showing previously fetched automation data; refresh to check again.</p>}
    <Load res={state} what="Loading automation state">{(s) => <Card as="article" title="Kill switch" aside={<StatusPill tone={s.paused === true ? 'warn' : 'ok'} label={s.paused === true ? 'Paused' : 'Running'} />}>
      {s.paused === true
        ? <p>All automation is paused. Rules do not fire until the owner resumes them.{typeof s.reason === 'string' && s.reason ? ` Reason: ${s.reason}` : ''}</p>
        : <p>Automation is running. Anything a rule files still needs approval unless you set a <Link to="/settings/standing-approvals">standing approval</Link>.</p>}
    </Card>}</Load>
    <Load res={rules} what="Loading automation rules">{(items) => <Card title="Rules">
      {items.length === 0 ? <p>No automation rules yet.</p> : <ul>{items.map((r, i) => <li key={typeof r.id === 'string' ? r.id : i}>
        <strong>{text(r.name, 'Unnamed rule')}</strong> <StatusPill tone={r.enabled === true ? 'ok' : 'neutral'} label={r.enabled === true ? 'On' : 'Off'} dot={false} />
        <dl className="om-facts">
          <div><dt>Trigger</dt><dd>{describeTrigger(r.trigger)}</dd></div>
          {nextFire(r.id) !== undefined && <div><dt>Next run</dt><dd>{nextFire(r.id)}</dd></div>}
          <div><dt>Last fired</dt><dd>{text(r.last_fired_at, 'Never')}</dd></div>
          <div><dt>Actions</dt><dd>{Array.isArray(r.actions) ? r.actions.length : 'Not reported'}</dd></div>
        </dl>
        {r.breaker !== null && r.breaker !== undefined && r.breaker !== 'closed' && <p className="om-note om-tone-warn">Stopped by its safety breaker after repeated failures ({typeof r.failures === 'number' ? r.failures : 'unknown'}).</p>}
      </li>)}</ul>}
    </Card>}</Load>
    <Load res={runs} what="Loading recent runs">{(items) => <Card title="Recent runs">
      {items.length === 0 ? <p>No runs yet.</p> : <ul>{items.map((r, i) => <li key={typeof r.id === 'string' ? r.id : i}>
        {ruleName(r.rule_id)} · {text(r.fired_at)} · {text(r.outcome)}{typeof r.detail === 'string' && r.detail ? ` (${r.detail})` : ''}
      </li>)}</ul>}
    </Card>}</Load>
    <Windows />
  </div>;
}

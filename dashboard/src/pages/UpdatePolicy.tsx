// SPDX-License-Identifier: Apache-2.0
// OS updates page, below the slots: the owner's update policy for apps (NMD-07, #132). Reads and writes
// /v1/update-policy through @onemind/sdk; the dry run answers "what would update tonight" and files
// nothing. The knobs only ever hold an update back; approving stays with the owner.
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load, useRun } from './parts';

export type UpdatePolicyBody = components['schemas']['UpdatePolicyBody'];
type Range = { days?: string[]; start: string; end: string };
export interface UpdatePolicyView extends UpdatePolicyBody {
  customized: boolean;
  updated_at: string | null;
  paused_apps: Array<{ app_id: string; failures: number }>;
}
interface DryRunItem {
  app_id: string; name: string; from_version: string | null; to_version: string; kind: string | null;
  released_at: string | null; outcome: 'would_update' | 'needs_approval' | 'held'; reason: string | null; until: string | null;
}
interface DryRun {
  evaluated_at: string; at: string; automation_paused: boolean;
  window: { id: string; name: string; open_now: boolean; next_open_at: string | null } | null;
  apps: DryRunItem[];
  ai: { enabled: boolean; off_now: boolean; next_change_at: string | null; apps: string[] };
}

/** Plain words for the gateway's reason codes (automation/updatepolicy.py, policies.py). */
export const REASONS: Record<string, string> = {
  cool_off: 'Too new: waiting out the cool-off',
  release_time_unknown: 'Release date unknown, so a person decides',
  major_update: 'New major version: only a person updates it',
  paused_after_failures: 'Paused after repeated failed updates',
  version_not_comparable: 'Versions cannot be compared',
  no_window: 'The chosen maintenance window does not exist',
  no_policy: 'No standing approval: it will wait in Approvals',
  automation_paused: 'Automation is paused',
};
const OUTCOME = {
  would_update: { tone: 'ok', label: 'Would update' },
  needs_approval: { tone: 'warn', label: 'Waits for approval' },
  held: { tone: 'bad', label: 'Held back' },
} as const;

function object(value: unknown, what: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ApiError(200, 'unknown', `The hub returned an invalid ${what}.`);
  return value as Record<string, unknown>;
}
function policy(value: unknown): UpdatePolicyView {
  const p = object(value, 'update policy');
  if (typeof p.cool_off_hours !== 'number' || typeof p.same_major_only !== 'boolean' || typeof p.backoff_after_failures !== 'number' || !Array.isArray(p.paused_apps)) throw new ApiError(200, 'unknown', 'The hub returned an invalid update policy.');
  return p as unknown as UpdatePolicyView;
}
function dryRun(value: unknown): DryRun {
  const d = object(value, 'dry run');
  if (!Array.isArray(d.apps) || !d.ai || typeof d.ai !== 'object') throw new ApiError(200, 'unknown', 'The hub returned an invalid dry run.');
  return d as unknown as DryRun;
}
async function call(client: OneMind, method: 'GET' | 'PUT' | 'POST', path: string, body?: unknown) {
  try { return await client.call<unknown>({ method, path, body }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : e.code === 'conflict' ? 'conflict' : 'unknown', e.message, e.reason);
    throw e;
  }
}
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : 'not scheduled');

export function UpdatePolicy() {
  const { token, person, mock } = useSignedIn();
  return mock
    ? <p role="status">Connect to a real hub to see its update policy. Demo mode has no update data.</p>
    : <LiveUpdatePolicy key={person} token={token} />;
}

function LiveUpdatePolicy({ token }: { token: string }) {
  const { canDecide } = useSignedIn();
  const run = useRun();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const current = usePoll(async () => policy(await call(client, 'GET', '/v1/update-policy')), 60_000);
  const dry = usePoll(async () => dryRun(await call(client, 'GET', '/v1/update-policy/dry-run')), 60_000);
  const [draft, setDraft] = useState<UpdatePolicyBody>();
  useEffect(() => {
    if (current.data && !draft) setDraft(pick(current.data));
  }, [current.data, draft]);
  const owner = canDecide !== 'no';
  const refresh = async () => { await current.reload(); await dry.reload(); };

  const save = (e: FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    void run(async () => {
      const saved = policy(await call(client, 'PUT', '/v1/update-policy', draft));
      setDraft(pick(saved));
      await refresh();
    }, 'Save update policy');
  };
  const resume = (appId: string) => void run(async () => {
    await call(client, 'POST', '/v1/update-policy/resume', { app_id: appId });
    await refresh();
  }, `Resume auto-update of ${appId}`);

  const range = (draft?.ai_schedule?.off?.[0] ?? { start: '23:00', end: '07:00' }) as Range;
  const setRange = (patch: Partial<Range>) => draft && setDraft({
    ...draft,
    ai_schedule: { enabled: false, tz: 'box', ...draft.ai_schedule, off: [{ ...range, ...patch }, ...(draft.ai_schedule?.off ?? []).slice(1)] },
  });

  return (
    <div className="dash-stack">
      <h2>App update policy</h2>
      <p className="om-hint">When apps may update on their own. These rules only hold an update back; an update still needs your approval or a standing approval you made.</p>
      <Load res={current} what="Loading the update policy">{(p) => <Card title="Update policy" level={2}>
        {!owner && <p className="om-note" role="status">Only the owner can change these rules.</p>}
        {draft && <form className="dash-form" onSubmit={save} aria-label="Update policy">
          <label htmlFor="up-cool">Cool-off after a release (hours)</label>
          <input id="up-cool" type="number" min={0} max={720} disabled={!owner} value={draft.cool_off_hours}
            onChange={(e) => setDraft({ ...draft, cool_off_hours: Number(e.target.value) })} />
          <label htmlFor="up-major">
            <input id="up-major" type="checkbox" disabled={!owner} checked={draft.same_major_only}
              onChange={(e) => setDraft({ ...draft, same_major_only: e.target.checked })} /> Same major version only
          </label>
          <label htmlFor="up-backoff">Pause auto-update after this many failures in a row</label>
          <input id="up-backoff" type="number" min={1} max={10} disabled={!owner} value={draft.backoff_after_failures}
            onChange={(e) => setDraft({ ...draft, backoff_after_failures: Number(e.target.value) })} />
          <fieldset>
            <legend>AI off to save power</legend>
            <label htmlFor="up-ai">
              <input id="up-ai" type="checkbox" disabled={!owner} checked={!!draft.ai_schedule?.enabled}
                onChange={(e) => setDraft({ ...draft, ai_schedule: { tz: 'box', off: [range], ...draft.ai_schedule, enabled: e.target.checked } })} /> Turn AI apps off on a schedule
            </label>
            <label htmlFor="up-ai-start">Off from</label>
            <input id="up-ai-start" type="time" disabled={!owner} value={range.start} onChange={(e) => setRange({ start: e.target.value })} />
            <label htmlFor="up-ai-end">Back on at</label>
            <input id="up-ai-end" type="time" disabled={!owner} value={range.end} onChange={(e) => setRange({ end: e.target.value })} />
            <p className="om-hint">Stopping and starting the AI apps at these times will be filed as requests that wait for you.</p>
          </fieldset>
          {owner && <Button type="submit">Save update policy</Button>}
        </form>}
        <p className="om-hint">{p.customized ? `Last changed ${when(p.updated_at)}.` : 'These are the defaults; nobody has changed them yet.'}</p>
        <h3>Paused apps</h3>
        {p.paused_apps.length === 0 ? <p>No app is paused.</p> : <ul>{p.paused_apps.map((a) => <li key={a.app_id}>
          <strong>{a.app_id}</strong>: {a.failures} failed updates in a row{' '}
          {owner && <Button size="sm" onClick={() => resume(a.app_id)}>Resume {a.app_id}</Button>}
        </li>)}</ul>}
      </Card>}</Load>
      <Load res={dry} what="Working out what would update">{(d) => <Card title="What would update tonight" level={2}
        aside={<Button size="sm" variant="ghost" onClick={() => void dry.reload()}>Check again</Button>}>
        <p>{d.window ? `Next window "${d.window.name}": ${d.window.open_now ? 'open now' : when(d.window.next_open_at)}.` : 'No maintenance window is set, so nothing updates on its own.'}
          {d.automation_paused ? ' Automation is paused.' : ''} This check files nothing.</p>
        {d.apps.length === 0 ? <p>Every installed app is up to date.</p> : <ul aria-label="Dry run">{d.apps.map((a) => <li key={a.app_id}>
          <strong>{a.name}</strong> {a.from_version ?? '?'} → {a.to_version}{' '}
          <StatusPill tone={OUTCOME[a.outcome].tone} label={OUTCOME[a.outcome].label} />
          {a.reason && a.outcome !== 'would_update' && <> · {REASONS[a.reason] ?? a.reason}</>}
          {a.until && <> · until {when(a.until)}</>}
        </li>)}</ul>}
        <h3>AI schedule</h3>
        <p>{!d.ai.enabled ? 'AI apps stay on.' : `AI apps are ${d.ai.off_now ? 'in their off hours' : 'in their on hours'}; next change ${when(d.ai.next_change_at)}.`}
          {' '}{d.ai.apps.length ? `Covers: ${d.ai.apps.join(', ')}.` : 'No AI app is installed.'}</p>
      </Card>}</Load>
    </div>
  );
}

function pick(p: UpdatePolicyView): UpdatePolicyBody {
  return { window_id: p.window_id, cool_off_hours: p.cool_off_hours, same_major_only: p.same_major_only, backoff_after_failures: p.backoff_after_failures, ai_schedule: p.ai_schedule };
}

// SPDX-License-Identifier: Apache-2.0
// Maintenance windows (GET /v1/windows, PUT /v1/windows/{id}): the weekly time ranges that standing
// approvals and update policy wait for. Editing one adds power, so only an owner may, and once the box
// has passkeys the gateway wants a fresh passkey sign-in first; this page says so in plain words and
// keeps the edits. Editing a window gives every standing approval that uses it a new revision.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { useShell } from '../../shell/Shell';
import { Load } from '../parts';
import { getJson, records, str, strs } from '../records';

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;
const DAY_WORD: Record<string, string> = { mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday', thu: 'Thursday', fri: 'Friday', sat: 'Saturday', sun: 'Sunday' };
interface Range { days: string[]; start: string; end: string }
interface Draft { id: string; name: string; tz: string; ranges: Range[]; isNew: boolean }

const blank = (): Range => ({ days: [...DAYS], start: '22:00', end: '06:00' });
const slug = (name: string) => `win_${name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 32)}`;

function describe(r: Range): string {
  const days = r.days.length === 0 || r.days.length === 7 ? 'Every day' : DAYS.filter((d) => r.days.includes(d)).map((d) => DAY_WORD[d]!.slice(0, 3)).join(', ');
  return `${days}, ${r.start} to ${r.end}${r.start > r.end ? ' (into the next morning)' : ''}`;
}
function ranges(v: unknown): Range[] {
  return records(v).map((r) => ({ days: strs(r.days).length ? strs(r.days) : [...DAYS], start: str(r.start, '00:00'), end: str(r.end, '00:00') }));
}
/** The gateway's own rule for a window id (WINDOW_ID_RE in core/onemind_core/routers/automation.py). */
const WINDOW_ID = /^win_[a-z0-9_]{1,36}$/;

function problem(d: Draft, taken: string[]): string {
  if (!d.name.trim()) return 'Give the window a name.';
  if (d.isNew && !WINDOW_ID.test(d.id)) return 'Use letters and numbers in the name so it can become an id.';
  // Saving is a PUT by id: a new window whose id already exists would silently replace that window.
  if (d.isNew && taken.includes(d.id)) return `A window with the id ${d.id} already exists. Give this one another name, or edit that window instead.`;
  if (d.ranges.length === 0) return 'Add at least one time range.';
  for (const r of d.ranges) {
    if (r.days.length === 0) return 'Pick at least one day in every range.';
    if (!r.start || !r.end || r.start === r.end) return 'Every range needs a start and a different end time.';
  }
  return '';
}

export function Windows() {
  const { token, person, mock } = useSignedIn();
  const { role } = useShell(); // a real hub's session has no principal; the role comes from GET /v1/me
  if (mock) return null;
  return <LiveWindows key={person} token={token} owner={role === 'owner'} roleKnown={role !== undefined} />;
}

function LiveWindows({ token, owner, roleKnown }: { token: string; owner: boolean; roleKnown: boolean }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const list = usePoll(async () => records(await getJson(sdk, '/v1/windows')), 30_000);
  const [draft, setDraft] = useState<Draft>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const patch = (p: Partial<Draft>) => setDraft((d) => d && { ...d, ...p });
  const setRange = (i: number, p: Partial<Range>) => setDraft((d) => d && { ...d, ranges: d.ranges.map((r, j) => (j === i ? { ...r, ...p } : r)) });
  const save = async () => {
    if (!draft || busy) return;
    let bad = problem(draft, (list.data ?? []).map((w) => str(w.id, '')));
    if (bad) { setError(bad); return; }
    setBusy(true); setError('');
    try {
      if (draft.isNew) {
        // Read the windows again right before the PUT, so one added on another device since the last poll is not replaced.
        bad = problem(draft, records(await getJson(sdk, '/v1/windows')).map((w) => str(w.id, '')));
        if (bad) { setError(bad); await list.reload(); return; }
      }
      await sdk.call<unknown>({ method: 'PUT', path: `/v1/windows/${encodeURIComponent(draft.id)}`, body: { name: draft.name.trim(), tz: draft.tz.trim() || 'box', ranges: draft.ranges.map((r) => ({ days: r.days, start: r.start, end: r.end })) } });
      setSaved(`Saved "${draft.name.trim()}". Standing approvals that use it were given a new revision.`); setDraft(undefined); await list.reload();
    } catch (e) {
      if (e instanceof OneMindError && e.reason === 'step_up_required') setError('This change needs your passkey. Sign out, sign in again with your passkey, then save again. Your edits are kept here until you leave the page.');
      else if (e instanceof OneMindError && e.status === 403) setError('Only an owner can edit a maintenance window.');
      else setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  return <section aria-label="Maintenance windows">
    <Load res={list} what="Loading maintenance windows">{(items) => <Card title="Maintenance windows" aside={owner && !draft ? <Button size="sm" onClick={() => { setSaved(''); setError(''); setDraft({ id: 'win_', name: '', tz: 'box', ranges: [blank()], isNew: true }); }}>Add a window</Button> : undefined}>
      <p className="om-note">A window is the weekly time when your box may do things on its own, such as installing updates. Standing approvals wait for their window to open.</p>
      {items.length === 0 ? <p>No windows yet.</p> : <ul>{items.map((w) => {
        const rs = ranges(w.ranges);
        return <li key={str(w.id)}>
          <strong>{str(w.name, str(w.id))}</strong> <StatusPill tone={w.open_now === true ? 'ok' : 'neutral'} label={w.open_now === true ? 'Open now' : 'Closed now'} dot={false} />
          <ul aria-label={`Times for ${str(w.name, str(w.id))}`}>{rs.map((r, i) => <li key={i}>{describe(r)}</li>)}</ul>
          <p className="om-note">Times are in {str(w.tz, 'box') === 'box' ? "this box's own time zone" : str(w.tz)}.</p>
          {owner && <Button size="sm" variant="secondary" onClick={() => { setSaved(''); setError(''); setDraft({ id: str(w.id), name: str(w.name, ''), tz: str(w.tz, 'box'), ranges: rs, isNew: false }); }}>Edit {str(w.name, str(w.id))}</Button>}
        </li>;
      })}</ul>}
      {!owner && roleKnown && <p className="om-note">Only an owner can change a window.</p>}
      {saved && <p role="status">{saved}</p>}
      {draft && <form aria-label={draft.isNew ? 'New window' : `Edit ${draft.name}`} onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <p><label htmlFor="win-name">Name</label>{' '}
          <input id="win-name" className="om-input" value={draft.name} maxLength={80} onChange={(e) => patch(draft.isNew ? { name: e.target.value, id: slug(e.target.value) } : { name: e.target.value })} autoComplete="off" /></p>
        {draft.isNew && <p className="om-note">Its id will be {draft.id}.</p>}
        <p><label htmlFor="win-tz">Time zone</label>{' '}
          <input id="win-tz" className="om-input" value={draft.tz} onChange={(e) => patch({ tz: e.target.value })} autoComplete="off" /> <span className="om-note">"box" means this box's own zone, or a name such as Europe/Berlin.</span></p>
        {draft.ranges.map((r, i) => <fieldset key={i}>
          <legend>Time range {i + 1}</legend>
          <div role="group" aria-label={`Days for range ${i + 1}`}>{DAYS.map((d) => <label key={d} style={{ marginRight: 12 }}>
            <input type="checkbox" checked={r.days.includes(d)} onChange={(e) => setRange(i, { days: e.target.checked ? [...r.days, d] : r.days.filter((x) => x !== d) })} /> {DAY_WORD[d]}</label>)}</div>
          <p><label htmlFor={`win-start-${i}`}>From</label>{' '}<input id={`win-start-${i}`} type="time" className="om-input" value={r.start} onChange={(e) => setRange(i, { start: e.target.value })} />{' '}
            <label htmlFor={`win-end-${i}`}>To</label>{' '}<input id={`win-end-${i}`} type="time" className="om-input" value={r.end} onChange={(e) => setRange(i, { end: e.target.value })} /></p>
          {draft.ranges.length > 1 && <Button size="sm" variant="ghost" onClick={() => patch({ ranges: draft.ranges.filter((_, j) => j !== i) })}>Remove range {i + 1}</Button>}
        </fieldset>)}
        {draft.ranges.length < 14 && <p><Button size="sm" variant="secondary" onClick={() => patch({ ranges: [...draft.ranges, blank()] })}>Add a time range</Button></p>}
        <p className="om-note">Changing a window gives every standing approval that uses it a new revision.</p>
        {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
        <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save window'}</Button>{' '}
        <Button variant="ghost" disabled={busy} onClick={() => { setDraft(undefined); setError(''); }}>Cancel</Button>
      </form>}
    </Card>}</Load>
  </section>;
}

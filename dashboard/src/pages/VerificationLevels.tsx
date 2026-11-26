// SPDX-License-Identifier: Apache-2.0
// Settings > Verification levels (D-028; gateway permissions design 3.11 and 3.12, design PR 16; issue #1213).
// The owner's table of how strongly OneMind checks it's you before each kind of approval or change: the
// level each row asks for now, its default, the lowest it may go and the highest. Destructive and physical
// approvals and every security setting ask for L2 (a proven key) by default; any single kind of request can
// be raised to L3 when a key on this box reaches it.
// Nothing here writes the table directly (BUILDER-BRIEFING item 6): a change files a
// verification.requirement.set request, which waits in Approvals until an owner approves it at the table's
// own level (L2 floor). The hub checks the floor and the ceiling again; this page only never offers a level
// a row can't take, so a first-time owner is not handed a choice that is refused afterwards.
// The same table is `onemind permissions verify get|set --json` in the CLI.
import { useState } from 'react';
import { Link } from 'react-router';
import { OneMindError, type Action, type components } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, Table, VerificationBadge, LEVEL_NAME, levelRank, type VerificationLevel } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway } from '../lib/gateway';
import { useSignedIn } from '../session';
import { Load } from './parts';

type VTable = components['schemas']['VerificationTable'];
type Row = components['schemas']['VerificationRow'];
type TypeRow = components['schemas']['VerificationType'];
type Bounds = Pick<Row, 'minimum' | 'maximum'>;

export const SET_TYPE = 'verification.requirement.set';
export const TYPE_PREFIX = 'type:';
const LEVELS: VerificationLevel[] = ['L0', 'L1', 'L2', 'L3'];

/** The levels a row may be set to: from its floor to its ceiling, and L3 only when a key on this box reaches
 *  it (nobody could approve anything at a level no key meets; the hub refuses that with level_unreachable). */
export function offeredLevels(row: Bounds, household: VTable['household_level']): VerificationLevel[] {
  const reach = household ? levelRank(household as VerificationLevel) : 0;
  return LEVELS.filter((l) => levelRank(l) >= levelRank(row.minimum as VerificationLevel) && levelRank(l) <= levelRank(row.maximum as VerificationLevel)
    && (l !== 'L3' || reach >= 3));
}

/** key -> level of each table change already waiting in Approvals. */
export function waitingChanges(actions: Pick<Action, 'type' | 'state' | 'params'>[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const a of actions) {
    if (a.type !== SET_TYPE || a.state !== 'awaiting_approval') continue;
    const p = (a.params ?? {}) as { key?: unknown; level?: unknown };
    if (typeof p.key === 'string' && typeof p.level === 'string') out[p.key] = p.level;
  }
  return out;
}

/** Plain words for why a change could not be filed. */
export function requestErrorText(e: unknown): string {
  if (e instanceof OneMindError) {
    if (e.reason === 'below_floor') return 'that row can\'t go that low. Nothing was filed.';
    if (e.reason === 'above_ceiling') return 'that row can\'t go that high: your own files never depend on a strong key. Nothing was filed.';
    if (e.reason === 'level_unreachable') return 'no key on this box reaches L3 yet, so nobody could approve it. Add a biometric-only key first.';
    if (e.reason === 'unknown_row') return 'OneMind doesn\'t know that kind of request. Check the name (for example app.remove).';
    if (e.status === 403) return 'only an owner can change this table.';
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export function VerificationLevels() {
  const { token, mock, principal } = useSignedIn();
  if (mock) return <><PageHeader title="Verification levels" /><Card title="Verification levels"><p role="status">Connect to a real hub to see its verification table. Demo mode has none.</p></Card></>;
  if (principal?.role !== 'owner') return <><PageHeader title="Verification levels" /><Card title="Verification levels"><p role="status">Only an owner can see and change how strongly OneMind checks approvals.</p></Card></>;
  return <LiveTable token={token} />;
}

function LiveTable({ token }: { token: string }) {
  const client = useGateway(token);
  const table = usePoll(() => client.call<VTable>({ method: 'GET', path: '/v1/verification-requirements' }), 0);
  // Requests this box has filed: changes already waiting in Approvals (so a row is not asked twice), and the
  // kinds of request it knows, as suggestions for a per-type check (real data; the hub checks the name again).
  const actions = usePoll(() => client.actions.list(), 0);
  const pending = waitingChanges(actions.data ?? []);
  const seenTypes = [...new Set((actions.data ?? []).map((a) => a.type).filter((x) => x !== SET_TYPE))].sort();
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string; id?: string }>();
  const [busy, setBusy] = useState(false);

  const request = async (key: string, level: string, what: string) => {
    setBusy(true); setNote(undefined);
    try {
      const a = await client.call<{ id: string }>({ method: 'POST', path: '/v1/actions', body: {
        type: SET_TYPE, params: { key, level },
        idempotency_key: `dash-verify-${key}-${level}-${Date.now().toString(36)}`,
        expires_at: new Date(client.hubNow() + 24 * 3600_000).toISOString(),
      } });
      setNote({ tone: 'ok', text: `Asked to set "${what}" to ${level} · ${LEVEL_NAME[level as VerificationLevel]}. It waits in Approvals for your proven key.`, id: a.id });
    } catch (e) {
      setNote({ tone: 'bad', text: `Changing "${what}": ${requestErrorText(e)}` });
    } finally { setBusy(false); void actions.reload(); }
  };

  return <div className="dash-stack">
    <PageHeader title="Verification levels" lede="How strongly OneMind checks it's you before each kind of approval or change. A higher level needs a stronger sign-in key." />
    <Load res={table} what="Loading the verification table">
      {(t) => <>
        <Household t={t} />
        <Card title="Which approvals need which level" subtitle="A change waits in Approvals until you approve it with a key at this table's own level.">
          <Table caption="Verification levels" hideCaption rows={t.rows} rowKey={(r) => r.key}
            columns={[
              { key: 'what', header: 'What', render: (r) => <>
                <strong>{r.label}</strong>
                <p className="om-hint">Default {r.default} · lowest {r.minimum} · highest {r.maximum}{r.strict ? ' · never eased before your first proven key' : ''}</p>
              </> },
              { key: 'now', header: 'Needs now', render: (r) => <VerificationBadge level={r.current as VerificationLevel} required /> },
              { key: 'change', header: 'Change', render: (r) => <Change key={`${r.key}-${r.current}`} label={r.label} bounds={r} current={r.current}
                options={offeredLevels(r, t.household_level)} waiting={pending[r.key]} busy={busy}
                onAsk={(level) => void request(r.key, level, r.label)} /> },
            ]} />
        </Card>
        <TypeOptIns t={t} pending={pending} busy={busy} seenTypes={seenTypes} onAsk={(type, level) => void request(`${TYPE_PREFIX}${type}`, level, type)} />
      </>}
    </Load>
    {note && <p role="status" className={`om-note om-tone-${note.tone}`}>{note.text}{note.id && <> <Link to="/approvals">Open Approvals</Link></>}</p>}
  </div>;
}

function Household({ t }: { t: VTable }) {
  return <Card title="Your box now" variant={t.recovery_needed ? 'attention' : 'default'}
    aside={t.household_level ? <VerificationBadge level={t.household_level as VerificationLevel} /> : <StatusPill tone="warn" label="No passkey yet" />}>
    <p>{t.household_level ? 'The badge is the strongest key an owner holds.' : 'No owner has a passkey yet.'} <Link to="/settings/sign-in-keys">Sign-in keys</Link></p>
    {t.grace && <p className="om-hint"><StatusPill tone="warn" label="Before your first proven key" /> Rows that need L2 accept any passkey plus the code on the box's own screen, so you confirm them standing at the box. Physical actions never do.{!t.box_confirm && ' This box has no screen to show that code, so those approvals wait for a proven key.'}</p>}
    {t.recovery_needed && <p className="om-hint"><StatusPill tone="bad" label="Waiting" /> Your box had a proven key and has none now. Approvals that need L2 wait until you add one at the box. They never go back to accepting a Device check key.</p>}
  </Card>;
}

function Change({ label, bounds, current, options, waiting, busy, onAsk }: {
  label: string; bounds: Bounds; current: string; options: VerificationLevel[]; waiting?: string; busy: boolean; onAsk: (level: string) => void;
}) {
  const [level, setLevel] = useState(current);
  if (waiting) return <StatusPill tone="info" label={`${waiting} waits in Approvals`} />;
  if (options.length <= 1) return <span className="om-hint">{bounds.minimum === bounds.maximum ? 'Fixed' : 'No stronger key on this box yet'}</span>;
  return <span className="dash-actions">
    <select aria-label={`New level for ${label}`} value={level} onChange={(e) => setLevel(e.target.value)}>
      {options.map((l) => <option key={l} value={l}>{l} · {LEVEL_NAME[l]}</option>)}
    </select>
    <Button size="sm" disabled={busy || level === current} aria-label={`Ask to change ${label}`} onClick={() => onAsk(level)}>Ask to change</Button>
  </span>;
}

function TypeOptIns({ t, pending, busy, seenTypes, onAsk }: {
  t: VTable; pending: Record<string, string>; busy: boolean; seenTypes: string[]; onAsk: (type: string, level: string) => void;
}) {
  const [type, setType] = useState('');
  const [level, setLevel] = useState<VerificationLevel>('L2');
  // A per-type row only raises (its floor is its tier's level), so a new one starts at L2.
  const choices = offeredLevels({ minimum: 'L2', maximum: 'L3' }, t.household_level);
  const clean = type.trim();
  return <Card title="Stronger checks for one kind of request" subtitle="Raise a single kind of request above its row, for example ask for a biometric-only key (L3) before an app is removed.">
    {t.types.length === 0 ? <p className="om-hint">No kind of request is raised yet. Each follows its row above.</p> : <Table
      caption="Raised kinds of request" hideCaption rows={t.types} rowKey={(r: TypeRow) => r.key}
      columns={[
        { key: 'type', header: 'Kind of request', render: (r: TypeRow) => <code>{r.key.slice(TYPE_PREFIX.length)}</code> },
        { key: 'now', header: 'Needs now', render: (r: TypeRow) => <VerificationBadge level={r.current as VerificationLevel} required /> },
        { key: 'change', header: 'Change', render: (r: TypeRow) => <Change key={`${r.key}-${r.current}`} label={r.key.slice(TYPE_PREFIX.length)} bounds={r} current={r.current}
          options={offeredLevels(r, t.household_level)} waiting={pending[r.key]} busy={busy} onAsk={(l) => onAsk(r.key.slice(TYPE_PREFIX.length), l)} /> },
      ]} />}
    <div className="dash-actions">
      <label>Kind of request{' '}<input value={type} maxLength={64} list="om-verify-types" placeholder="app.remove" onChange={(e) => setType(e.target.value)} /></label>
      <datalist id="om-verify-types">{seenTypes.map((x) => <option key={x} value={x} />)}</datalist>
      <label>Level{' '}<select value={level} onChange={(e) => setLevel(e.target.value as VerificationLevel)}>
        {choices.map((l) => <option key={l} value={l}>{l} · {LEVEL_NAME[l]}</option>)}
      </select></label>
      <Button disabled={busy || !clean || !!pending[`${TYPE_PREFIX}${clean}`]} onClick={() => { onAsk(clean, level); setType(''); }}>Ask for this check</Button>
    </div>
    {!t.household_level || levelRank(t.household_level as VerificationLevel) < 3 ? <p className="om-hint">L3 appears here once a key on this box reaches it.</p> : null}
  </Card>;
}

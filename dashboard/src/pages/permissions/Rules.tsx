// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions > Rules (design §3.6, §3.6.2): the standing approvals that answer for you.
// GET /v1/approval-policies; POST …/{id}/revoke (one tap, no passkey: ending a rule only narrows),
// POST …/revoke-all, PATCH …/{id} (narrowing applies at once; widening asks for the passkey),
// POST …/{id}/reconfirm (a suspended rule, passkey), POST …/{id}/keep (a forever rule's 90-day review).
// A rule's history comes from the audit log (GET /v1/audit/events).
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { explain, read, usePermSdk, useStepUp } from '../../lib/permissions';
import { Load } from '../parts';
import { NOTIFY, day, history, historyLine, idleReason, lifetime, limitsLine, live, ruleLine, suspendedWhy, usesLine, type Rule } from './ruleText';

const RULES = '/v1/approval-policies';

export function Rules({ item }: { item?: string }) {
  const sdk = usePermSdk();
  const stepUp = useStepUp();
  const rules = usePoll(() => read(sdk.call<Rule[]>({ method: 'GET', path: RULES })), 0);
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string }>();
  const [endAll, setEndAll] = useState(false);

  const act = async (job: () => Promise<unknown>, ok: string) => {
    try {
      await job();
      setNote({ tone: 'ok', text: ok });
    } catch (e) {
      setNote({ tone: 'bad', text: explain(e) });
    }
    await rules.reload();
  };
  const post = (id: string, verb: string, passkey = false) => {
    const send = (client: typeof sdk) => client.call<Rule>({ method: 'POST', path: `${RULES}/${encodeURIComponent(id)}/${verb}` });
    return passkey ? stepUp(send, sdk) : read(send(sdk));
  };
  const revoke = (r: Rule) => act(() => post(r.id, 'revoke'), `Revoked: ${r.name || ruleLine(r)}. It will not approve anything again.`);

  return (
    <Load res={rules} what="Loading rules">
      {(list) => {
        const rule = item ? list.find((r) => r.id === item) : undefined;
        if (item) return rule
          ? <RuleDetail rule={rule} note={note} onRevoke={() => void revoke(rule)}
              onReconfirm={() => void act(() => post(rule.id, 'reconfirm', true), 'Re-confirmed. The rule works again.')}
              onKeep={() => void act(() => post(rule.id, 'keep'), 'Kept. You will be asked again in 90 days.')}
              onNarrow={(body) => act(() => stepUp((c) => c.call<Rule>({ method: 'PATCH', path: `${RULES}/${encodeURIComponent(rule.id)}`, body: { ...body, revision: rule.revision } }), sdk), 'Saved as a new revision.')} />
          : <Gone note={note} />;
        const active = list.filter(live).sort((a, b) => Number(b.forever) - Number(a.forever) || a.created_at.localeCompare(b.created_at));
        const ended = list.filter((r) => !live(r));
        return (
          <>
            {note && <p className={`om-note om-tone-${note.tone}`} role={note.tone === 'bad' ? 'alert' : 'status'}>{note.text}</p>}
            <Card title={`Rules that answer for you (${active.length})`} subtitle="A rule lets one requester do one kind of thing without asking you, within limits. Rules only work for requesters on Ask once, Auto or Headless."
              aside={active.length > 1 ? <Button size="sm" variant="secondary" onClick={() => setEndAll(true)}>Revoke all</Button> : undefined}>
              {active.length === 0 ? (
                <p className="om-hint">No rules yet. On an approval card, choose “Approve and remember” to make one for requests like it.</p>
              ) : (
                <ul className="dash-list" aria-label="Rules in force">
                  {active.map((r) => <li key={r.id}><RuleCard rule={r} onRevoke={() => void revoke(r)} /></li>)}
                </ul>
              )}
            </Card>
            {ended.length > 0 && (
              <details>
                <summary>Ended rules ({ended.length})</summary>
                <ul className="dash-list" aria-label="Ended rules">
                  {ended.map((r) => <li key={r.id}><Link to={`/settings/permissions/rules/${encodeURIComponent(r.id)}`}>{r.name || ruleLine(r)}</Link> <span className="om-hint">{r.state}{r.revoked_at ? ` on ${day(r.revoked_at)}` : ''}</span></li>)}
                </ul>
              </details>
            )}
            {endAll && (
              <Dialog open role="alertdialog" title="Revoke every rule?" description="Every request will wait for you again. You can make new rules from approval cards." onClose={() => setEndAll(false)}
                actions={<><Button onClick={() => setEndAll(false)}>Cancel</Button><Button variant="primary" onClick={() => { setEndAll(false); void act(() => read(sdk.call({ method: 'POST', path: `${RULES}/revoke-all`, body: { principal: null } })), 'Every rule is revoked.'); }}>Revoke all</Button></>} />
            )}
          </>
        );
      }}
    </Load>
  );
}

/**
 * A rule page whose rule is not listed: the gateway lists only rules still in force, so it was revoked
 * or has ended. Right after Revoke on this page, the note says so instead.
 */
function Gone({ note }: { note?: { tone: 'ok' | 'bad'; text: string } }) {
  return (
    <>
      {note
        ? <p className={`om-note om-tone-${note.tone}`} role={note.tone === 'bad' ? 'alert' : 'status'}>{note.text}</p>
        : <p className="om-note om-tone-warn" role="status">This rule was revoked or has ended, so it no longer approves anything.</p>}
      <p><Link to="/settings/permissions/rules">See all rules</Link></p>
    </>
  );
}

function Badges({ rule }: { rule: Rule }) {
  return (
    <span className="dash-actions">
      {rule.forever && <StatusPill tone="warn" label="Forever" />}
      {rule.state === 'suspended' && <StatusPill tone="bad" label="Suspended" />}
      {rule.state === 'paused' && <StatusPill tone="neutral" label="Paused" />}
      {rule.review_due && <StatusPill tone="warn" label="Review due" />}
      {!live(rule) && <StatusPill tone="neutral" label={rule.state} />}
    </span>
  );
}

function Facts({ rule }: { rule: Rule }) {
  const idle = live(rule) ? idleReason(rule) : undefined;
  return (
    <>
      <p>{ruleLine(rule)}</p>
      <p className="om-hint">{lifetime(rule)} · {limitsLine(rule)}</p>
      <p className="om-hint">{usesLine(rule)} · {NOTIFY[rule.notify_after] ?? rule.notify_after}</p>
      {rule.state === 'suspended' && <p className="om-note om-tone-warn">Suspended because {suspendedWhy(rule.suspended_reason)}. It approves nothing until you re-confirm it.</p>}
      {idle && <p className="om-note om-tone-info">{idle}</p>}
    </>
  );
}

function RuleCard({ rule, onRevoke }: { rule: Rule; onRevoke: () => void }) {
  const title = rule.name || ruleLine(rule);
  return (
    <Card as="article" level={3} title={title} aside={<Badges rule={rule} />}
      footer={<div className="dash-actions">
        <Link to={`/settings/permissions/rules/${encodeURIComponent(rule.id)}`} aria-label={`Details for ${title}`}>Details</Link>
        <Button size="sm" variant="secondary" aria-label={`Revoke ${title}`} onClick={onRevoke}>Revoke</Button>
      </div>}>
      <Facts rule={rule} />
    </Card>
  );
}

interface NarrowBody { limits?: { per_day?: number; max_uses?: number }; expires_at?: string }

function RuleDetail({ rule, note, onRevoke, onReconfirm, onKeep, onNarrow }: {
  rule: Rule; note?: { tone: 'ok' | 'bad'; text: string }; onRevoke: () => void; onReconfirm: () => void; onKeep: () => void; onNarrow: (b: NarrowBody) => Promise<void>;
}) {
  const sdk = usePermSdk();
  const past = usePoll(() => read(history(sdk, rule)), 0);
  const [perDay, setPerDay] = useState(String(rule.limits.per_day));
  const [maxUses, setMaxUses] = useState(rule.limits.max_uses ? String(rule.limits.max_uses) : '');
  const [ends, setEnds] = useState(rule.expires_at ? rule.expires_at.slice(0, 10) : '');
  const title = rule.name || ruleLine(rule);
  const save = (e: FormEvent) => {
    e.preventDefault();
    const limits: NarrowBody['limits'] = {};
    if (Number(perDay) !== rule.limits.per_day) limits.per_day = Number(perDay);
    if (maxUses && Number(maxUses) !== rule.limits.max_uses) limits.max_uses = Number(maxUses);
    const body: NarrowBody = Object.keys(limits).length ? { limits } : {};
    if (ends && ends !== rule.expires_at?.slice(0, 10)) body.expires_at = new Date(`${ends}T23:59:59Z`).toISOString();
    if (Object.keys(body).length) void onNarrow(body);
  };
  return (
    <>
      <p><Link to="/settings/permissions/rules">All rules</Link></p>
      {note && <p className={`om-note om-tone-${note.tone}`} role={note.tone === 'bad' ? 'alert' : 'status'}>{note.text}</p>}
      <Card title={title} subtitle={`Revision ${rule.revision} · made ${day(rule.created_at)}${rule.created_from ? ' from an approval' : ''}`} aside={<Badges rule={rule} />}
        footer={live(rule) ? <div className="dash-actions">
          {rule.state === 'suspended' && <Button variant="primary" onClick={onReconfirm}>Re-confirm with passkey</Button>}
          {rule.review_due && <Button onClick={onKeep}>Keep this rule</Button>}
          <Button variant="secondary" onClick={onRevoke}>Revoke</Button>
        </div> : undefined}>
        <Facts rule={rule} />
      </Card>
      {live(rule) && (
        <Card title="Change limits" subtitle="Lowering a limit or ending sooner applies at once. Anything that widens the rule asks for your passkey.">
          <form onSubmit={save} className="dash-stack">
            <label>Uses per day <input type="number" min={1} max={1000} required value={perDay} onChange={(e) => setPerDay(e.target.value)} /></label>
            <label>Uses in total (optional) <input type="number" min={1} max={100000} value={maxUses} onChange={(e) => setMaxUses(e.target.value)} /></label>
            {!rule.forever && <label>Ends on <input type="date" value={ends} onChange={(e) => setEnds(e.target.value)} /></label>}
            <div><Button type="submit">Save changes</Button></div>
          </form>
        </Card>
      )}
      <Card title="History">
        <Load res={past} what="Loading the rule’s history">
          {(rows) => rows.length === 0 ? <p className="om-hint">No history recorded yet.</p> : (
            <ol className="dash-list" aria-label="Rule history">
              {rows.map((x) => <li key={x.seq}><span className="om-hint">{day(x.ts)}</span> {historyLine(x)}</li>)}
            </ol>
          )}
        </Load>
      </Card>
    </>
  );
}

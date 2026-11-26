// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions > Auto-approved (design §3.8, §3.12 "Auto-approved log"): every request one of
// your rules approved in the last 30 days, newest first, each with Revoke rule (one tap, no passkey).
// Read from the audit log: GET /v1/audit/events?event=action.approved, the lines with approved_via=policy.
// The daily summary notice (approval.auto.digest) links here.
import { useState } from 'react';
import { Link } from 'react-router';
import { Button, Card, StatusPill } from '@onemind/ui';
import type { OneMind } from '@onemind/sdk';
import { usePoll } from '../../lib/hooks';
import { explain, read, usePermSdk } from '../../lib/permissions';
import { Load } from '../parts';
import { day, type AuditRecord } from './ruleText';

export const DAYS = 30;

interface Use { seq: number; ts: string; actionId: string | null; type: string; who: string; policyId: string; revision?: number; uses?: string; forever: boolean }

export async function autoApproved(sdk: OneMind, now = Date.now()): Promise<Use[]> {
  const since = new Date(now - DAYS * 86400_000).toISOString();
  const out: Use[] = [];
  let after: number | undefined;
  for (let page = 0; page < 10; page++) {
    const { records, more } = await sdk.audit.list({ event: 'action.approved', since, afterSeq: after, limit: 500 });
    for (const r of records as AuditRecord[]) {
      const d = (r.data ?? {}) as Record<string, unknown>;
      if (d.approved_via !== 'policy' || typeof d.policy_id !== 'string') continue;
      out.push({ seq: r.seq, ts: r.ts, actionId: r.action_id ?? null, type: String(d.type ?? ''), who: String(d.requested_by ?? ''),
        policyId: d.policy_id, revision: typeof d.policy_revision === 'number' ? d.policy_revision : undefined,
        uses: typeof d.uses === 'string' ? d.uses : undefined, forever: d.forever === true });
    }
    if (!more || !records.length) break;
    after = records[records.length - 1]!.seq;
  }
  return out.reverse();
}

export function AutoApproved() {
  const sdk = usePermSdk();
  const log = usePoll(() => read(autoApproved(sdk)), 60_000);
  const [ended, setEnded] = useState<Record<string, true>>({});
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string }>();
  const revoke = async (policyId: string) => {
    try {
      await read(sdk.call({ method: 'POST', path: `/v1/approval-policies/${encodeURIComponent(policyId)}/revoke` }));
      setEnded((e) => ({ ...e, [policyId]: true }));
      setNote({ tone: 'ok', text: 'Rule revoked. Requests like these will wait for you again.' });
    } catch (e) {
      setNote({ tone: 'bad', text: explain(e) });
    }
  };
  return (
    <Load res={log} what="Loading what your rules approved">
      {(rows) => (
        <>
          {note && <p className={`om-note om-tone-${note.tone}`} role={note.tone === 'bad' ? 'alert' : 'status'}>{note.text}</p>}
          <Card title={`Approved by your rules (${rows.length})`} subtitle={`Every request a rule approved for you in the last ${DAYS} days. If one is not what you meant, revoke the rule.`}>
            {rows.length === 0 ? <p className="om-hint">Nothing was approved by a rule in the last {DAYS} days.</p> : (
              <ul className="dash-list" aria-label="Approved by your rules">
                {rows.map((u) => (
                  <li key={u.seq} className="dash-actions">
                    <span>
                      <strong>{u.type}</strong> for {u.who.replace(/^agent:/, '')} <span className="om-hint">· {day(u.ts)}{u.uses ? ` · use ${u.uses} that day` : ''}</span>{' '}
                      <Link to={`/settings/permissions/rules/${encodeURIComponent(u.policyId)}`}>Rule{u.revision ? `, revision ${u.revision}` : ''}</Link>
                      {u.forever && <> <StatusPill tone="warn" label="Forever" /></>}
                    </span>
                    {ended[u.policyId]
                      ? <span className="om-hint">Rule revoked</span>
                      : <Button size="sm" variant="secondary" aria-label={`Revoke the rule that approved ${u.type} on ${day(u.ts)}`} onClick={() => void revoke(u.policyId)}>Revoke rule</Button>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </Load>
  );
}

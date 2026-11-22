// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import type { OneMind, StatusView } from '@onemind/sdk';
import { ACTION_STATE, ApprovalCard, Button, Card } from '@onemind/ui';
import type { Action } from '../../api/types';
import type { AlertInfo } from '../../api/wiring';
import { toActionSummary } from '../../data/adapters';
import { approveWithStepUp } from '../../lib/approve';
import { usePoll } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { useBusy, useRun } from '../parts';
import { CHECKS } from './ReportProblem';

function FixRequest({ id, client }: { id: string; client: OneMind }) {
  const { api, canDecide } = useSignedIn();
  const [busy, withBusy] = useBusy();
  const run = useRun();
  const actionId = encodeURIComponent(id);
  const res = usePoll(() => client.call<Action>({ method: 'GET', path: `/v1/actions/${actionId}` }), 3000);
  const action = res.data;
  if (res.error || !action?.params || !Object.hasOwn(ACTION_STATE, action.state)) {
    return <p role="status">{res.loading ? 'Reading fix request…' : 'Fix progress unknown.'}</p>;
  }
  const decide = (approve: boolean) => void withBusy(async () => {
    await run(async () => {
      if (approve) {
        const me = await api.me();
        await approveWithStepUp(api, action, { passkey: me.step_up.passkeys_active });
      } else {
        await api.deny(id);
      }
    }, 'Could not decide the fix request');
    await res.reload();
  });
  return <ApprovalCard action={toActionSummary(action)} now={client.hubNow()} canDecide={canDecide === 'no' ? { allowed: false, reason: 'This sign-in cannot approve a request.' } : { allowed: true }}
    busy={busy} onApprove={() => decide(true)} onDeny={() => decide(false)}
    extra={action.plan && <details><summary>Review plan</summary><pre>{JSON.stringify(action.plan, null, 2)}</pre></details>} />;
}

export function FixProblem({ client, status, owner }: { client: OneMind; status?: StatusView; owner: boolean }) {
  const { canRequest } = useSignedIn();
  const alerts = usePoll(async () => {
    const open = await client.call<AlertInfo[]>({ method: 'GET', path: '/v1/alerts?state=open' });
    return open.filter(a => a.fix && (a.state === 'open' || a.state === 'acknowledged'));
  }, 15_000);
  const [requests, setRequests] = useState<Record<string, string>>({});
  const [busy, withBusy] = useBusy();
  const run = useRun();
  const fix = (id: string) => void withBusy(() => run(async () => {
    const alertId = encodeURIComponent(id);
    const action = await client.call<Action>({ method: 'POST', path: `/v1/alerts/${alertId}/fix` });
    if (!action?.id) throw new Error('The box did not identify the fix request.');
    setRequests(old => ({ ...old, [id]: action.id }));
  }, 'Could not request the fix'));
  const attention = CHECKS.filter(name => status?.[name]?.state !== 'ok');
  return <Card title="Fix a problem">
    {status ? attention.length > 0 ? <ul>{attention.map(name => {
      const check = status[name];
      return <li key={name}>{name}: {check?.state ?? 'unknown'}{check?.summary && ' — ' + check.summary}</li>;
    })}</ul> : <p>No box check needs attention.</p> : <p>Box checks unknown.</p>}
    {alerts.error ? <p>Open alerts unknown.</p> : alerts.data && <ul>{alerts.data.map(a => <li key={a.id}>
      {a.title}{' '}
      {owner && canRequest !== 'no' && !requests[a.id] && <Button aria-label={'Fix ' + a.title} disabled={busy} onClick={() => fix(a.id)}>Fix</Button>}
    </li>)}</ul>}
    {Object.entries(requests).map(([alert, id]) => <FixRequest key={alert + id} id={id} client={client} />)}
  </Card>;
}

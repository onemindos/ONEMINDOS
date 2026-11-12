// SPDX-License-Identifier: Apache-2.0
// Approvals (IA §2.4): everything waiting for a human, then recent decisions.
import { useState } from 'react';
import { ACTION_STATE, ApprovalCard, EmptyState, PageHeader, StatusPill, Table, actionTitle, formatAgo, secondsSince, useToast, type ActionSummary } from '../../../src';
import { Section } from '../bits';
import { NOW, decided, pending } from '../fixtures';

export function Approvals() {
  const toast = useToast();
  const [items, setItems] = useState(pending);
  const [done, setDone] = useState(decided);
  const decide = (a: ActionSummary, d: 'approve' | 'deny') => {
    setItems((xs) => xs.filter((x) => x.id !== a.id));
    setDone((xs) => [{ ...a, state: d === 'approve' ? 'dispatched' : 'cancelled', decided_by: { id: 'person:owner', kind: 'person' } }, ...xs]);
    toast.show({ tone: d === 'approve' ? 'ok' : 'neutral', title: `${d === 'approve' ? 'Approved' : 'Denied'}: ${actionTitle(a)}`, body: d === 'approve' ? 'Running now. Follow it in Activity.' : undefined });
  };
  return (
    <>
      <PageHeader title="Approvals" lede="Nothing changes on your box until a person approves it. Agents can ask; they can never approve." />
      <Section title={`Waiting (${items.length})`}>
        {items.length === 0 ? (
          <EmptyState icon="check" title="Nothing is waiting" command="GET /v1/actions?state=awaiting_approval">
            New requests from people, agents and automatic updates appear here and on your phone.
          </EmptyState>
        ) : (
          <div className="d-grid">
            {items.map((a) => (
              <ApprovalCard key={a.id} action={a} now={NOW} canDecide={{ allowed: true }} onApprove={(x) => decide(x, 'approve')} onDeny={(x) => decide(x, 'deny')} />
            ))}
          </div>
        )}
      </Section>
      <Section title="Recent decisions">
        <Table
          caption="Recent decisions"
          hideCaption
          rowKey={(r) => r.id}
          initialSort={{ key: 'when', dir: 'desc' }}
          columns={[
            { key: 'what', header: 'Request', render: (r) => <strong>{actionTitle(r)}</strong> },
            { key: 'by', header: 'Asked by', render: (r) => <StatusPill tone={r.requested_by?.kind === 'agent' ? 'agent' : 'neutral'} label={r.requested_by?.id ?? 'unknown'} dot={false} /> },
            { key: 'dec', header: 'Decided by', secondary: true, render: (r) => r.decided_by?.id ?? '—' },
            { key: 'when', header: 'When', sortValue: (r) => Date.parse(r.created_at ?? '0'), render: (r) => formatAgo(secondsSince(r.created_at ?? '', NOW)) },
            { key: 'state', header: 'Result', render: (r) => <StatusPill tone={ACTION_STATE[r.state].tone} label={ACTION_STATE[r.state].label} /> },
          ]}
          rows={done}
        />
      </Section>
    </>
  );
}

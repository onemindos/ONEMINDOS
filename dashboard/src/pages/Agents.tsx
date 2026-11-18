// SPDX-License-Identifier: Apache-2.0
// AI & Agents audit (report ch. 3): what every agent asked for and what a person decided. It reads
// the hash-chained audit log (GET /v1/audit/events, GET /v1/audit/verify; audit:read, owner and
// adult) and keeps the records an agent wrote plus the decisions and results of its requests.
// When the chain cannot be read it falls back to the agents' requests (GET /v1/actions) and says
// so. Read only: agents never act here, and every agent request still waits in Approvals.
import { useCallback, useMemo } from 'react';
import { AuditTimeline, Card, Table, formatAgo, secondsSince, type ActivityData, type Column, type SettingsLoadable } from '@onemind/ui';
import { activityFrom } from '../data/adapters';
import { agentRecords, agentSummaries, toActivity, type AgentSummary } from '../data/audit';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

export const AGENTS_NOTE =
  'Built from the agents’ requests on this hub (GET /v1/actions). The hash-chained audit log could not be read with this account (GET /v1/audit/events).';

const PAGE = 500;

/** The page reads one window of the chain, so it says how far back it goes. */
export const AGENTS_WINDOW_NOTE = `Covers the latest ${PAGE} audit events on this hub; older agent activity is not shown here.`;

export function Agents() {
  const hub = useHub();
  const { api } = useSignedIn();
  const audit = usePoll(
    useCallback(async () => {
      const verify = await api.auditVerify();
      const head = verify.head?.seq ?? 0;
      const records = await api.auditEvents({ limit: PAGE, after_seq: Math.max(0, head - PAGE) });
      return { verify, records: agentRecords(records) };
    }, [api]),
    30_000,
  );
  const agentActions = useMemo(() => hub.actionList.filter((a) => a.requested_by?.kind === 'agent'), [hub.actionList]);

  const cols: Column<AgentSummary>[] = [
    { key: 'id', header: 'Agent', render: (r) => r.id, sortValue: (r) => r.id },
    { key: 'requests', header: 'Requests', render: (r) => String(r.requests), sortValue: (r) => r.requests, align: 'end' },
    { key: 'approved', header: 'Approved', render: (r) => String(r.approved), align: 'end' },
    { key: 'denied', header: 'Denied', render: (r) => String(r.denied), align: 'end' },
    { key: 'last', header: 'Last seen', render: (r) => formatAgo(secondsSince(r.last, hub.now)), secondary: true },
  ];

  const head = { title: 'AI & Agents', lede: 'What each agent asked for and what a person decided. Agents only ever file requests; an owner approves each one.' };

  if (audit.data) {
    const { verify, records } = audit.data;
    const data: SettingsLoadable<ActivityData> = { status: 'ready', data: toActivity(records, verify), asOf: new Date(audit.fetchedAt ?? Date.now()).toISOString() };
    return (
      <div className="dash-stack">
        <AuditTimeline {...head} data={data} now={hub.now} onVerify={() => void audit.reload()} onRetry={() => void audit.reload()} />
        <p className="om-hint">{AGENTS_WINDOW_NOTE}</p>
        <Card title="Agents" variant="sunken">
          <Table caption="Agents" hideCaption columns={cols} rows={agentSummaries(records)} rowKey={(r) => r.id} empty="No agent has made a request yet." />
        </Card>
      </div>
    );
  }
  if (!audit.error && audit.loading) {
    return <AuditTimeline {...head} data={{ status: 'loading' }} now={hub.now} calls={['GET /v1/audit/events']} />;
  }

  const fallback: SettingsLoadable<ActivityData> =
    hub.actions.data !== undefined
      ? { status: 'ready', data: { entries: activityFrom(agentActions, hub.appName) }, asOf: hub.asOf ?? new Date().toISOString(), stale: hub.freshness === 'stale' || hub.freshness === 'offline' }
      : hub.actions.error
        ? { status: 'error', error: { error: 'unavailable', message: hub.actions.error.message } }
        : { status: 'loading' };
  return <AuditTimeline {...head} data={fallback} now={hub.now} onRetry={hub.reloadAll} chainNote={AGENTS_NOTE} calls={['GET /v1/actions']} />;
}

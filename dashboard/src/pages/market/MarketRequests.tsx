// SPDX-License-Identifier: Apache-2.0
// Atlas Market (04): Requests. Every app request the hub knows about, waiting ones first, read from
// GET /v1/actions through the shared hub poll. Read only: deciding stays in Approvals and on the
// app page's waiting track, both of which go through the same passkey step-up (D-027).
import { EmptyState, PageHeader, StatusPill, type Tone } from '@onemind/ui';
import type { ActionState } from '../../api/types';
import { appIdOf } from '../../data/adapters';
import { useHub } from '../../data/hub';
import { formatAgo, secondsSince } from '../../lib/time';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';
import { MarketLayout } from './MarketSidebar';
import { askedBy, isAppRequest, requestVerb, sortRequests } from './requests';

const STATE: Record<ActionState, { tone: Tone; label: string }> = {
  requested: { tone: 'neutral', label: 'Sent' },
  awaiting_approval: { tone: 'warn', label: 'Waiting for approval' },
  accepted: { tone: 'info', label: 'Approved' },
  dispatched: { tone: 'info', label: 'Working' },
  succeeded: { tone: 'ok', label: 'Done' },
  failed: { tone: 'bad', label: 'Failed' },
  outcome_unknown: { tone: 'bad', label: 'Outcome unknown' },
  expired: { tone: 'neutral', label: 'Ran out of time' },
  cancelled: { tone: 'neutral', label: 'Cancelled' },
};

export function MarketRequests() {
  const hub = useHub();
  const { account, principal } = useSignedIn();
  const me = account ?? principal;
  const list = sortRequests(hub.actionList.filter(isAppRequest));
  const loaded = hub.actions.data !== undefined;
  return (
    <MarketLayout current="requests">
      <PageHeader title="Requests" lede="App installs, updates and removals asked for on this box. Nothing runs until an owner approves it." />
      {!loaded && (hub.actions.error ? <p role="alert">Could not read requests: {hub.actions.error.message}</p> : <p role="status">Loading requests…</p>)}
      {loaded && hub.actions.error && <p className="om-note om-tone-warn" role="status">Could not refresh. Showing the last answer from the hub.</p>}
      {loaded && list.length === 0 && (
        <EmptyState icon="approvals" title="No app requests" command="onemind actions list">
          <p>Requests appear here when someone asks to install, update or remove an app.</p>
        </EmptyState>
      )}
      {list.length > 0 && (
        <ul className="dash-mkt-requests" aria-label="App requests">
          {list.map((a) => {
            const appId = appIdOf(a)!;
            const st = STATE[a.state] ?? { tone: 'neutral' as Tone, label: a.state.replace(/_/g, ' ') };
            const at = a.created_at ? formatAgo(secondsSince(a.created_at, hub.now)) : 'time not reported';
            return (
              <li key={a.id} className="dash-mkt-request">
                <div>
                  <a href={href.app(appId)} className="dash-mkt-request-title">{requestVerb(a)} {hub.appName(appId)}</a>
                  <p className="om-hint">Asked by {askedBy(a, me)} · {at}</p>
                </div>
                <StatusPill tone={st.tone} label={st.label} />
                {a.state === 'awaiting_approval' && <a href={href.approval(a.id)}>Review in Approvals</a>}
              </li>
            );
          })}
        </ul>
      )}
    </MarketLayout>
  );
}

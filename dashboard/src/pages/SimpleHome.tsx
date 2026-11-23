// SPDX-License-Identifier: Apache-2.0
// UX-01 (#206): the Home a child or guest gets (roles.ts view 'simple'). Three plain cards, all
// read from the hub: my apps, my requests, family status. No Needs you widget, no System, no
// Approvals: they cannot decide anything, and the hub would refuse the data anyway.
import { Card, PageHeader, StateView, StatusPill } from '@onemind/ui';
import { openUrl } from '../data/adapters';
import { errorText, useHub } from '../data/hub';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { HomeRecent } from './HomeRecent';
import { useShell } from '../shell/Shell';

const WORDS: Record<string, string> = {
  requested: 'Sent', awaiting_approval: 'Waiting for a parent or owner', accepted: 'Approved', dispatched: 'Working on it',
  succeeded: 'Done', failed: 'Did not work', outcome_unknown: 'Not sure yet', expired: 'Ran out of time', cancelled: 'Cancelled',
};

export function SimpleHome() {
  const hub = useHub();
  const { principal } = useSignedIn();
  const shell = useShell();
  const apps = (hub.apps.data ?? []).filter((a) => a.installed);
  const running = apps.filter((a) => a.status === 'running').length;
  const mine = hub.actionList.filter((a) => !principal || !a.requested_by || a.requested_by.id === principal.id);
  const requestsOff = hub.actions.error?.code === 'permission_denied';
  return (
    <div className="dash-stack">
      <PageHeader title="Home" lede={shell.role === 'child' ? 'Your apps and requests.' : 'Your apps and how the household is doing.'} />
      <Card title="My apps" as="section">
        {hub.apps.error ? (
          <p role="alert">Could not load your apps: {errorText(hub.apps.error).message}</p>
        ) : hub.apps.data === undefined ? (
          <StateView state="loading" what="Your apps" skeleton="list" />
        ) : apps.length === 0 ? (
          <p>No apps are installed yet. <a href={href.market}>Look in the Market</a>.</p>
        ) : (
          <ul className="dash-list" aria-label="My apps">
            {apps.map((a) => {
              const url = openUrl(a);
              return (
                <li key={a.id}>
                  {url ? <a href={url} target="_blank" rel="noopener noreferrer">{a.name ?? a.id}<span className="om-visually-hidden"> (opens in a new tab)</span></a> : <a href={href.app(a.id)}>{a.name ?? a.id}</a>}{' '}
                  <StatusPill tone={a.status === 'running' ? 'ok' : 'warn'} label={a.status === 'running' ? 'Running' : a.status.replace(/_/g, ' ')} />
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      <Card title="My requests" as="section">
        {requestsOff ? (
          <p>Your account cannot see requests. If you want an app, ask a parent.</p>
        ) : hub.actions.error ? (
          <p role="alert">Could not load your requests: {errorText(hub.actions.error).message}</p>
        ) : hub.actions.data === undefined ? (
          <StateView state="loading" what="Your requests" skeleton="list" />
        ) : mine.length === 0 ? (
          <p>You have not asked for anything.</p>
        ) : (
          <ul className="dash-list" aria-label="My requests">
            {mine.map((a) => (
              <li key={a.id}>
                {a.type.replace(/^app\./, '').replace(/_/g, ' ')} {hub.appName(String(a.params.app_id ?? ''))}: {WORDS[a.state] ?? a.state.replace(/_/g, ' ')}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Family status" as="section">
        {hub.apps.data === undefined ? (
          <StateView state="loading" what="Family status" skeleton="list" />
        ) : (
          <p role="status">
            {hub.freshness === 'live' ? 'The hub is answering.' : 'The hub is not answering right now.'}{' '}
            {apps.length === 0 ? 'No apps installed.' : running === apps.length ? `All ${apps.length} apps are running.` : `${running} of ${apps.length} apps are running.`}
          </p>
        )}
      </Card>
      {shell.role && shell.role !== 'agent' && <HomeRecent />}
    </div>
  );
}

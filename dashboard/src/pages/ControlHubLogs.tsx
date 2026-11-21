// SPDX-License-Identifier: Apache-2.0
// Control Hub, Logs tab: the last lines an installed app wrote (GET /v1/apps/{id}/logs, owners and
// adults), in the shared @onemind/ui LogViewer. Read-only: nothing here changes the box.
import { useMemo } from 'react';
import { Button, LogViewer } from '@onemind/ui';
import { parseLogs } from '../data/logs';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load } from './parts';

export function LogsPanel({ appId }: { appId: string }) {
  const { api } = useSignedIn();
  const logs = usePoll(async () => {
    if (!api.appLogs) throw new Error('Logs cannot be read by this gateway client.');
    return api.appLogs(appId);
  }, 0);
  const parsed = useMemo(() => (logs.data === undefined ? undefined : parseLogs(logs.data, new Date(logs.fetchedAt ?? Date.now()))), [logs.data, logs.fetchedAt]);
  return (
    <Load res={logs} what="Loading logs">
      {() => parsed && (
        <div className="dash-stack">
          <LogViewer appId={appId} lines={parsed.lines} state={{ kind: 'ready', fetched_at: new Date(logs.fetchedAt ?? Date.now()).toISOString() }} now={logs.fetchedAt ?? Date.now()} />
          {parsed.untimed > 0 && <p className="om-hint">The hub does not time-stamp every line, so {parsed.untimed === parsed.lines.length ? 'the times shown are' : `${parsed.untimed} of the times shown are`} when the lines were read, not when the app wrote them.</p>}
          <div><Button size="sm" onClick={() => void logs.reload()}>Refresh logs</Button></div>
        </div>
      )}
    </Load>
  );
}

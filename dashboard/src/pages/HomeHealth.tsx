// SPDX-License-Identifier: Apache-2.0
// The aggregate status is authoritative. Details can add backup ages and available versions.
import { BoxHealth, type HomeStatusRow } from '@onemind/ui';
import { healthRows } from '../data/healthSummary';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';

const quiet = <T,>(p: Promise<T> | undefined) => (p ?? Promise.resolve(undefined)).catch(() => undefined);

/** `pro`: the person may open Backups (an owner or adult); otherwise that row is text, as on the Home widgets. */
export function HomeHealth({ pro, status }: { pro: boolean; status: HomeStatusRow[] }) {
  const { api } = useSignedIn();
  const hub = useHub();
  const backup = usePoll(() => quiet(api.backupsStatus?.()), 60_000);
  const monitoring = usePoll(() => quiet(api.monitoring()), 30_000);
  const updates = usePoll(() => quiet(api.osUpdates?.()), 300_000);
  const rows = healthRows(
    { backup: backup.data, openAlerts: monitoring.data?.open_alerts, updates: updates.data, now: hub.now },
    { backups: pro ? href.setting('backups') : '', alerts: href.alerts, updates: href.setting('updates') },
  );
  const details = Object.fromEntries(rows.flatMap((row) => {
    const source = { backup: 'backups', update: 'updates', alerts: 'alerts' }[row.id];
    const state = { ok: 'ok', warn: 'attention', bad: 'critical', neutral: undefined }[row.tone];
    return state && status.some((item) => item.source === source && item.state === state) ? [[source, row.value]] : [];
  }));
  return <BoxHealth rows={status} details={details} links={{
    alerts: href.alerts, approvals: href.approvals, apps: href.installed, storage: href.storage,
    backups: pro ? href.setting('backups') : '', updates: href.setting('updates'), mesh: href.nodes,
  }} />;
}

// SPDX-License-Identifier: Apache-2.0
// The health card at the top of Home: last backup, critical alerts, update available. Read-only;
// each row links to the screen that acts on it. A route a role may not read shows "Not reported".
import { Link } from 'react-router';
import { StatusPill } from '@onemind/ui';
import { healthRows } from '../data/healthSummary';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';

const TONE = { ok: 'ok', warn: 'warn', bad: 'bad', neutral: 'neutral' } as const;
const quiet = <T,>(p: Promise<T> | undefined) => (p ?? Promise.resolve(undefined)).catch(() => undefined);

/** `pro`: the person may open Backups (an owner or adult); otherwise that row is text, as on the Home widgets. */
export function HomeHealth({ pro }: { pro: boolean }) {
  const { api } = useSignedIn();
  const hub = useHub();
  const backup = usePoll(() => quiet(api.backupsStatus?.()), 60_000);
  const monitoring = usePoll(() => quiet(api.monitoring()), 30_000);
  const updates = usePoll(() => quiet(api.osUpdates?.()), 300_000);
  if (backup.loading || monitoring.loading || updates.loading) return null;
  const rows = healthRows(
    { backup: backup.data, openAlerts: monitoring.data?.open_alerts, updates: updates.data, now: hub.now },
    { backups: pro ? href.setting('backups') : '', alerts: href.alerts, updates: href.setting('updates') },
  );
  return (
    <section className="dash-health" aria-label="Box health">
      <ul>
        {rows.map((r) => (
          <li key={r.id}>
            {(() => {
              const body = <><span className="dash-health-label">{r.label}</span><StatusPill tone={TONE[r.tone]} label={r.value} /></>;
              return r.href ? <Link to={r.href}>{body}</Link> : <span className="dash-health-row">{body}</span>;
            })()}
          </li>
        ))}
      </ul>
    </section>
  );
}

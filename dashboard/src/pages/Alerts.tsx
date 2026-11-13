// SPDX-License-Identifier: Apache-2.0
// Monitoring: the summary (GET /v1/monitoring/summary) and open alerts (GET /v1/alerts).
// "Ask to fix" calls POST /v1/alerts/{id}/fix with approve=false, so the fix becomes a request in
// Approvals and nothing changes until a person approves it there. Acknowledge and resolve only
// change the alert's own state. Alert text comes from the hub and is shown as text.
import { Link } from 'react-router';
import { Button, Card, PageHeader, StatusPill, useToast, type Tone } from '@onemind/ui';
import type { AlertInfo, Severity } from '../api/wiring';
import { useHub } from '../data/hub';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { formatAgo, secondsSince } from '../lib/time';
import { href } from '../shell/routes';
import { useSignedIn } from '../session';
import { Load, useRun } from './parts';

const TONE: Record<Severity, Tone> = { info: 'info', warning: 'warn', critical: 'bad' };

export function Alerts() {
  const { api, principal } = useSignedIn();
  const hub = useHub();
  const run = useRun();
  const toast = useToast();
  const summary = usePoll(() => api.monitoring(), 30_000);
  const alerts = usePoll(() => api.alerts('open'), 15_000);
  const isOwner = principal?.role === 'owner' || hub.canDecide === 'unknown';

  const fix = (a: AlertInfo) =>
    void run(async () => {
      await api.askToFix(a.id);
      toast.show({ tone: 'info', title: t('alerts.fix.sent'), body: a.fix?.label ?? a.title });
      hub.reloadAll();
    }, t('alerts.fix', { title: a.title }));

  return (
    <div className="dash-stack">
      <PageHeader title={t('alerts.title')} lede={t('alerts.lede')} />
      <Load res={summary} what="Loading the summary">
        {(s) => (
          <Card title="Right now" variant="sunken">
            <dl className="om-facts">
              <div><dt>Nodes online</dt><dd>{s.nodes.online} of {s.nodes.online + s.nodes.stale + s.nodes.offline}</dd></div>
              <div><dt>Apps healthy</dt><dd>{s.apps.healthy ?? 0}</dd></div>
              <div><dt>Apps unhealthy</dt><dd>{s.apps.unhealthy ?? 0}</dd></div>
              <div><dt>Open alerts</dt><dd>{s.open_alerts.critical} critical, {s.open_alerts.warning} warning, {s.open_alerts.info} info</dd></div>
            </dl>
          </Card>
        )}
      </Load>
      <Load res={alerts} what="Loading alerts">
        {(rows) =>
          rows.length === 0 ? (
            <p className="om-hint">{t('alerts.none')}</p>
          ) : (
            <ul className="dash-list" aria-label={t('alerts.title')}>
              {rows.map((a) => (
                <li key={a.id}>
                  <Card as="article" level={3} title={a.title} variant={a.severity === 'critical' ? 'attention' : 'default'} aside={<StatusPill tone={TONE[a.severity]} label={a.severity} detail={a.state} />}>
                    {a.body && <p>{a.body}</p>}
                    <p className="om-hint">
                      Opened {formatAgo(secondsSince(a.opened_at, hub.now))}
                      {a.occurrences > 1 ? `, seen ${a.occurrences} times` : ''}
                      {a.flapping ? ', keeps flapping' : ''}
                    </p>
                    <div className="dash-actions">
                      {a.state === 'open' && (
                        <Button size="sm" variant="secondary" aria-label={t('alerts.ack', { title: a.title })} onClick={() => void run(async () => { await api.ackAlert(a.id); await alerts.reload(); }, t('alerts.ack', { title: a.title }))}>
                          Acknowledge
                        </Button>
                      )}
                      {a.fix && (
                        <Button size="sm" variant="primary" aria-label={t('alerts.fix', { title: a.title })} onClick={() => fix(a)}>
                          Ask to fix
                        </Button>
                      )}
                      {isOwner && (
                        <Button size="sm" variant="ghost" aria-label={t('alerts.resolve', { title: a.title })} onClick={() => void run(async () => { await api.resolveAlert(a.id); await alerts.reload(); }, t('alerts.resolve', { title: a.title }))}>
                          Resolve
                        </Button>
                      )}
                      {a.fix && <Link to={href.approvals}>Open Approvals</Link>}
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </Load>
    </div>
  );
}

// SPDX-License-Identifier: Apache-2.0
// Notifications: your inbox (GET /v1/notifications, mark read) and your channels
// (GET/POST/DELETE /v1/notifications/channels, POST …/test). Channels cover the two kinds that need
// one address (a push topic or a webhook); email has more fields and stays on the API for now.
// Notification text comes from the hub and is rendered as text, never as HTML.
import { useState, type FormEvent } from 'react';
import { Button, Card, Dialog, PageHeader, StatusPill, type Tone } from '@onemind/ui';
import type { NotificationItem, Severity } from '../api/wiring';
import { useHub } from '../data/hub';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { formatAgo, secondsSince } from '../lib/time';
import { toRoute } from '../shell/routes';
import { useSignedIn } from '../session';
import { Link } from 'react-router';
import { Load, TextField, useRun } from './parts';

const TONE: Record<Severity, Tone> = { info: 'info', warning: 'warn', critical: 'bad' };
const KINDS = [
  { id: 'unifiedpush', label: 'Push topic (ntfy, UnifiedPush)' },
  { id: 'webhook', label: 'Webhook' },
] as const;

export function Inbox() {
  const { api } = useSignedIn();
  const hub = useHub();
  const run = useRun();
  const inbox = usePoll(() => api.notifications({ limit: 100 }), 30_000);
  const channels = usePoll(() => api.channels(), 0);
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<string>('unifiedpush');
  const [label, setLabel] = useState('');
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const urlOk = /^https?:\/\/[^\s/@]+(\/\S*)?$/.test(url.trim());

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!label.trim() || !urlOk) return;
    void run(async () => {
      await api.createChannel({ kind, label: label.trim(), config: { url: url.trim() }, ...(secret ? { secret } : {}) });
      setAdding(false);
      setLabel('');
      setUrl('');
      setSecret('');
      await channels.reload();
    }, t('inbox.channels.add'));
  };
  const open = (n: NotificationItem) => {
    void run(async () => {
      if (!n.read_at) await api.markRead(n.id);
      await inbox.reload();
    }, 'Mark as read');
  };

  return (
    <div className="dash-stack">
      <PageHeader title={t('inbox.title')} lede={t('inbox.lede')} actions={<Button size="sm" variant="secondary" onClick={() => void run(async () => { await api.markAllRead(); await inbox.reload(); }, t('inbox.readAll'))}>{t('inbox.readAll')}</Button>} />
      <Load res={inbox} what="Loading notifications">
        {(rows) =>
          rows.length === 0 ? (
            <p className="om-hint">{t('inbox.none')}</p>
          ) : (
            <ul className="dash-list" aria-label={t('inbox.title')}>
              {rows.map((n) => {
                const to = n.link ? toRoute(n.link) : undefined;
                return (
                  <li key={n.id}>
                    <Card as="article" title={n.title} level={3} variant={n.read_at ? 'default' : 'attention'} aside={<StatusPill tone={TONE[n.severity]} label={n.severity} />}>
                      {n.body && <p>{n.body}</p>}
                      <p className="om-hint">
                        {n.topic} · {formatAgo(secondsSince(n.created_at, hub.now))}
                      </p>
                      <div className="dash-actions">
                        {to && <Link to={to}>Open</Link>}
                        {!n.read_at && (
                          <Button size="sm" variant="ghost" aria-label={`Mark as read: ${n.title}`} onClick={() => open(n)}>
                            Mark as read
                          </Button>
                        )}
                      </div>
                    </Card>
                  </li>
                );
              })}
            </ul>
          )
        }
      </Load>
      <Card title={t('inbox.channels')} aside={<Button size="sm" icon="plus" onClick={() => setAdding(true)}>{t('inbox.channels.add')}</Button>}>
        <Load res={channels} what="Loading channels">
          {(rows) =>
            rows.length === 0 ? (
              <p className="om-hint">{t('inbox.channels.none')}</p>
            ) : (
              <ul className="dash-list" aria-label={t('inbox.channels')}>
                {rows.map((c) => (
                  <li key={c.id} className="dash-actions">
                    <strong>{c.label}</strong>
                    <StatusPill tone={c.last_error ? 'bad' : c.verified ? 'ok' : 'neutral'} label={c.last_error ? 'Failing' : c.verified ? 'Verified' : 'Not tested'} detail={c.kind} />
                    <Button size="sm" variant="ghost" aria-label={t('inbox.channels.test', { label: c.label })} onClick={() => void run(async () => { await api.testChannel(c.id); await channels.reload(); }, t('inbox.channels.test', { label: c.label }))}>
                      Send test
                    </Button>
                    <Button size="sm" variant="danger" aria-label={t('inbox.channels.remove', { label: c.label })} onClick={() => void run(async () => { await api.deleteChannel(c.id); await channels.reload(); }, t('inbox.channels.remove', { label: c.label }))}>
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )
          }
        </Load>
      </Card>
      <Dialog open={adding} onClose={() => setAdding(false)} title={t('inbox.channels.add')} actions={<><Button variant="ghost" onClick={() => setAdding(false)}>{t('common.cancel')}</Button><Button variant="primary" onClick={add} disabled={!label.trim() || !urlOk}>{t('common.save')}</Button></>}>
        <form className="dash-form" onSubmit={add}>
          <label htmlFor="chan-kind">{t('inbox.channels.kind')}</label>
          <select id="chan-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.id} value={k.id}>{k.label}</option>
            ))}
          </select>
          <TextField id="chan-label" label={t('inbox.channels.label')} value={label} onChange={setLabel} />
          <TextField id="chan-url" label={t('inbox.channels.url')} value={url} onChange={setUrl} type="url" />
          <TextField id="chan-secret" label={t('inbox.channels.secret')} value={secret} onChange={setSecret} type="password" />
        </form>
      </Dialog>
    </div>
  );
}

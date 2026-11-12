// SPDX-License-Identifier: Apache-2.0
// Settings > Account and security: who you are (GET /v1/me), your passkeys and where you are
// signed in. Adding a passkey runs the browser's WebAuthn ceremony; removing a passkey or signing
// a device out only takes power away, so it happens at once (the gateway still audits it).
import { Button, Card, PageHeader, StatusPill, Table, useToast } from '@onemind/ui';
import { useHub } from '../data/hub';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { createPasskey, webauthnSupported } from '../lib/webauthn';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Load, useRun } from './parts';

const ago = (iso: string | null | undefined, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : t('common.never'));

export function Account() {
  const { api, signOut } = useSignedIn();
  const hub = useHub();
  const toast = useToast();
  const run = useRun();
  const me = usePoll(() => api.me(), 0);
  const passkeys = usePoll(() => api.passkeys(), 0);
  const sessions = usePoll(() => api.sessions(), 0);

  const addPasskey = () =>
    void run(async () => {
      const o = await api.passkeyRegisterOptions();
      const credential = await createPasskey(o.publicKey);
      await api.passkeyRegister(credential, 'Dashboard passkey');
      toast.show({ tone: 'ok', title: t('account.passkeys.added') });
      await Promise.all([passkeys.reload(), me.reload()]);
    }, t('account.passkeys.add'));

  return (
    <div className="dash-stack">
      <PageHeader title={t('account.title')} lede={t('account.lede')} />
      <Load res={me} what="Loading your account">
        {(m) => (
          <Card title={m.principal.display_name ?? m.principal.id} subtitle={`${m.principal.kind}${m.principal.role ? `, ${m.principal.role}` : ''}`} aside={<Button variant="ghost" onClick={signOut}>{t('account.signout')}</Button>}>
            <p className="om-hint">{t('account.stepup')}</p>
            <StatusPill tone={m.step_up.passkeys_active ? 'ok' : 'neutral'} label={m.step_up.passkeys_active ? 'Passkeys active' : 'No passkey yet'} />
          </Card>
        )}
      </Load>
      <Card title={t('account.passkeys')} aside={webauthnSupported() ? <Button size="sm" icon="plus" onClick={addPasskey}>{t('account.passkeys.add')}</Button> : <span className="om-hint">{t('account.passkeys.unsupported')}</span>}>
        <Load res={passkeys} what="Loading passkeys">
          {(rows) =>
            rows.length === 0 ? (
              <p className="om-hint">{t('account.passkeys.none')}</p>
            ) : (
              <Table
                caption={t('account.passkeys')}
                hideCaption
                rows={rows}
                rowKey={(r) => r.credential_id}
                columns={[
                  { key: 'label', header: 'Name', render: (r) => r.label ?? 'Passkey' },
                  { key: 'created', header: 'Added', render: (r) => ago(r.created_at, hub.now), secondary: true },
                  { key: 'used', header: 'Last used', render: (r) => ago(r.last_used_at, hub.now), secondary: true },
                  {
                    key: 'x',
                    header: 'Actions',
                    render: (r) => (
                      <Button size="sm" variant="ghost" aria-label={t('account.passkeys.remove', { name: r.label ?? 'passkey' })} onClick={() => void run(async () => { await api.deletePasskey(r.credential_id); await passkeys.reload(); }, t('account.passkeys.remove', { name: r.label ?? 'passkey' }))}>
                        Remove
                      </Button>
                    ),
                  },
                ]}
              />
            )
          }
        </Load>
      </Card>
      <Card title={t('account.sessions')}>
        <Load res={sessions} what="Loading sessions">
          {(rows) => (
            <Table
              caption={t('account.sessions')}
              hideCaption
              rows={rows}
              rowKey={(r) => r.id}
              columns={[
                { key: 'client', header: 'Where', render: (r) => (r.current ? `${r.client} (${t('account.sessions.current')})` : r.client) },
                { key: 'how', header: 'How', render: (r) => r.auth_method, secondary: true },
                { key: 'seen', header: 'Last seen', render: (r) => ago(r.last_seen_at, hub.now), secondary: true },
                {
                  key: 'x',
                  header: 'Actions',
                  render: (r) =>
                    r.current ? null : (
                      <Button size="sm" variant="ghost" aria-label={t('account.sessions.revoke', { name: r.client })} onClick={() => void run(async () => { await api.revokeSession(r.id); await sessions.reload(); }, t('account.sessions.revoke', { name: r.client }))}>
                        Sign out
                      </Button>
                    ),
                },
              ]}
            />
          )}
        </Load>
      </Card>
    </div>
  );
}

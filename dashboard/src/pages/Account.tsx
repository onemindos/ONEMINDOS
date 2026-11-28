// SPDX-License-Identifier: Apache-2.0
// Settings > Account and security: who you are (GET /v1/me), your passkeys and where you are
// signed in. Adding a passkey runs the browser's WebAuthn ceremony; removing a passkey or signing
// a device out only takes power away, so it happens at once (the gateway still audits it).
// App passwords (WebDAV for Finder and Linux file managers, #722) are in AppPasswords.tsx; the owner's SSH keys and
// SSH switch (P-06) are in SshKeys.tsx; recovery contacts (25d, D-028) in RecoveryContacts.tsx.
import { useState, type FormEvent } from 'react';
import { Button, Card, PageHeader, StatusPill, Table, useToast } from '@onemind/ui';
import { useHub } from '../data/hub';
import { AccountSignIn } from './AccountSignIn';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { registerPasskey } from '../lib/registerPasskey';
import { webauthnSupported } from '../lib/webauthn';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { AppPasswords } from './AppPasswords';
import { SshKeys } from './SshKeys';
import { RecoveryContacts } from './RecoveryContacts';
import { IdentityFactors } from './IdentityFactors';
import { MyDevices } from './MyDevices';
import { Load, TextField, useBusy, useRun } from './parts';

const ago = (iso: string | null | undefined, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : t('common.never'));

function ChangePassword() {
  const { api } = useSignedIn();
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [busy, run] = useBusy();
  const [error, setError] = useState<string>();
  const toast = useToast();
  const dismiss = () => { setEditing(false); setCurrent(''); setNext(''); setError(undefined); };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if ([...next].length < 12) { setError(t('setup.short')); return; }
    void run(async () => {
      setError(undefined);
      try {
        await api.changePassword?.({ current_password: current, new_password: next });
        dismiss();
        toast.show({ tone: 'ok', title: t('account.password.saved') });
      } catch (e) { setError(e instanceof Error ? e.message : t('factors.failed')); }
    });
  };
  return editing ? <form className="dash-form" onSubmit={submit}>
    <TextField id="change-current-password" label={t('account.password.current')} type="password" autoComplete="current-password" value={current} onChange={setCurrent} />
    <TextField id="change-new-password" label={t('setup.password')} type="password" autoComplete="new-password" value={next} onChange={setNext} />
    {error && <p role="alert">{error}</p>}
    <div className="dash-identity-actions">
      <Button type="submit" disabled={busy || !current || !next}>{t('account.password.change')}</Button>
      <Button type="button" variant="ghost" onClick={dismiss} disabled={busy}>{t('common.cancel')}</Button>
    </div>
  </form> : <Button onClick={() => setEditing(true)}>{t('account.password.change')}</Button>;
}

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
      await registerPasskey(api, 'Dashboard passkey');
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
      {(api.changePassword || api.setupTotp || api.updateIdentityEmail) && <Card title="Sign-in methods">
        {api.changePassword && <ChangePassword />}
        <IdentityFactors api={api} offerEmail email={me.data?.email} emailVerified={me.data?.email_verified} totp={me.data?.totp} reload={me.reload} />
      </Card>}
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
      {/* The Sign-in methods card above covers password and authenticator code (D-034). AccountSignIn is the
          standalone screen for a client without those calls, so the page never shows the controls twice. */}
      {!api.changePassword && !api.setupTotp && <AccountSignIn />}
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
                        {t('account.signout')}
                      </Button>
                    ),
                },
              ]}
            />
          )}
        </Load>
      </Card>
      <RecoveryContacts />
      <MyDevices />
      <AppPasswords />
      <SshKeys />
    </div>
  );
}

// SPDX-License-Identifier: Apache-2.0
// Settings > People (owner only): GET/POST /v1/users, PATCH /v1/users/{id}, POST …/disable. These
// are the owner's own acts in their own session; the gateway enforces owner-only, step-up and the
// "last owner" guard. An invite code is shown once in a dialog and never stored.
import { useState, type FormEvent } from 'react';
import { Button, Card, Dialog, PageHeader, StatusPill, Table } from '@onemind/ui';
import type { PersonRole, UserInfo } from '../api/wiring';
import { useHub } from '../data/hub';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Load, OneTimeDialog, TextField, useRun } from './parts';

const ROLES: PersonRole[] = ['adult', 'guest', 'owner'];

export function Users() {
  const { api } = useSignedIn();
  const hub = useHub();
  const run = useRun();
  const users = usePoll(() => api.users(), 0);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState<PersonRole>('adult');
  const [code, setCode] = useState<{ secret: string; name: string }>();
  const [confirm, setConfirm] = useState<UserInfo>();

  const create = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    void run(async () => {
      const u = await api.createUser({ display_name: name.trim(), role });
      setAdding(false);
      setName('');
      setCode({ secret: u.one_time.enrolment_code, name: u.display_name });
      await users.reload();
    }, t('users.add'));
  };

  return (
    <div className="dash-stack">
      <PageHeader title={t('users.title')} lede={t('users.lede')} />
      <Card title={t('users.title')} aside={<Button size="sm" icon="plus" onClick={() => setAdding(true)}>{t('users.add')}</Button>}>
        <Load res={users} what="Loading people">
          {(rows) => (
            <Table
              caption={t('users.title')}
              hideCaption
              rows={rows}
              rowKey={(r) => r.id}
              columns={[
                { key: 'name', header: t('users.name'), render: (r) => r.display_name, sortValue: (r) => r.display_name },
                {
                  key: 'role',
                  header: t('users.role'),
                  render: (r) => (
                    <select
                      aria-label={`${t('users.role')}: ${r.display_name}`}
                      value={r.role}
                      disabled={r.disabled}
                      onChange={(e) => void run(async () => { await api.updateUser(r.id, { role: e.target.value as PersonRole }); await users.reload(); }, t('users.role'))}
                    >
                      {ROLES.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  ),
                },
                { key: 'state', header: 'Status', render: (r) => <StatusPill tone={r.disabled ? 'bad' : r.enrolled ? 'ok' : 'warn'} label={r.disabled ? 'Disabled' : r.enrolled ? 'Active' : 'Invited'} />, secondary: true },
                { key: 'seen', header: 'Last seen', render: (r) => (r.last_seen_at ? formatAgo(secondsSince(r.last_seen_at, hub.now)) : t('common.never')), secondary: true },
                {
                  key: 'x',
                  header: 'Actions',
                  render: (r) => (r.disabled ? null : <Button size="sm" variant="danger" aria-label={t('users.disable', { name: r.display_name })} onClick={() => setConfirm(r)}>Disable</Button>),
                },
              ]}
            />
          )}
        </Load>
      </Card>
      <Dialog open={adding} onClose={() => setAdding(false)} title={t('users.invite.title')} actions={<><Button variant="ghost" onClick={() => setAdding(false)}>{t('common.cancel')}</Button><Button variant="primary" onClick={create}>{t('users.invite.submit')}</Button></>}>
        <form className="dash-form" onSubmit={create}>
          <TextField id="invite-name" label={t('users.name')} value={name} onChange={setName} />
          <label htmlFor="invite-role">{t('users.role')}</label>
          <select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as PersonRole)}>
            {ROLES.map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </form>
      </Dialog>
      <Dialog open={!!confirm} role="alertdialog" onClose={() => setConfirm(undefined)} title={t('users.disable', { name: confirm?.display_name ?? '' })} description={t('users.disable.confirm', { name: confirm?.display_name ?? '' })} actions={<><Button variant="ghost" onClick={() => setConfirm(undefined)}>{t('common.cancel')}</Button><Button variant="danger" onClick={() => { const u = confirm; setConfirm(undefined); if (u) void run(async () => { await api.disableUser(u.id); await users.reload(); }, t('users.disable', { name: u.display_name })); }}>Disable</Button></>} />
      <OneTimeDialog title={t('users.add')} note={t('users.invite.done', { name: code?.name ?? '' })} secret={code?.secret} onClose={() => setCode(undefined)} />
    </div>
  );
}

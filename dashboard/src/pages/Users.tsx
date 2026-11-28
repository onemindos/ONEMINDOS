// SPDX-License-Identifier: Apache-2.0
// Settings > People: signed-in owners verify new invitations in place. Replacing
// an existing invitation clears the account's credentials and goes to Approvals.
import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { Button, Card, Dialog, PageHeader, StatusPill, Table } from '@onemind/ui';
import { AGE_PRESETS, type PersonRole, type UserCreated, type UserInfo } from '../api/wiring';
import { useHub } from '../data/hub';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { InviteDialog } from './InviteDialog';
import { Load, TextField, useBusy, useRun } from './parts';

const ROLES: PersonRole[] = ['adult', 'teen', 'child', 'guest', 'owner'];

/** Read-only: the person's real age-rating limit, marked as the default while it still equals the role preset. */
function AgeRating({ user }: { user: UserInfo }) {
  const { api } = useSignedIn();
  const [max, setMax] = useState<number | null | undefined>();
  useEffect(() => {
    let live = true;
    setMax(undefined);
    api.familyProfile(user.id).then((p) => live && setMax(p.max_age_rating ?? null), () => undefined);
    return () => { live = false; };
  }, [api, user.id, user.role]);
  if (max === undefined) return null;
  const text = max === null ? t('users.age.none')
    : max === AGE_PRESETS[user.role] ? t('users.age.default', { max: String(max), who: user.role === 'teen' ? 'teens' : 'children' })
    : t('users.age.set', { max: String(max) });
  return <div className="om-hint">{text}</div>;
}

export function Users() {
  const { api } = useSignedIn();
  const hub = useHub();
  const navigate = useNavigate();
  const run = useRun();
  const [busy, whileBusy] = useBusy();
  const users = usePoll(() => api.users(), 0);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState<PersonRole>('adult');
  const [invite, setInvite] = useState<UserCreated>();
  const [confirm, setConfirm] = useState<UserInfo>();
  const [replace, setReplace] = useState<UserInfo>();

  const create = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    void whileBusy(() => run(async () => {
      const result = await api.createUser({ display_name: name.trim(), role });
      setAdding(false);
      setName('');
      setInvite(result);
      await users.reload();
    }, t('users.add')));
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
                { key: 'name', header: t('users.name'), render: (r) => (r.role === 'child' || r.role === 'teen' ? <><div>{r.display_name}</div><AgeRating user={r} /></> : r.display_name), sortValue: (r) => r.display_name },
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
                  render: (r) => r.disabled ? null : <div className="dash-identity-actions">
                    {api.reissueInvite && r.role !== 'owner' && <Button size="sm" aria-label={t('users.invite.reset', { name: r.display_name })} onClick={() => setReplace(r)}>{t('users.invite.replace')}</Button>}
                    <Button size="sm" variant="danger" aria-label={t('users.disable', { name: r.display_name })} onClick={() => setConfirm(r)}>Disable</Button>
                  </div>,
                },
              ]}
            />
          )}
        </Load>
      </Card>
      <Dialog open={adding} onClose={() => setAdding(false)} title={t('users.invite.title')} actions={<><Button variant="ghost" onClick={() => setAdding(false)}>{t('common.cancel')}</Button><Button variant="primary" busy={busy} onClick={create}>{t('users.invite.submit')}</Button></>}>
        <form className="dash-form" onSubmit={create}>
          <TextField id="invite-name" label={t('users.name')} value={name} onChange={setName} />
          <label htmlFor="invite-role">{t('users.role')}</label>
          <select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as PersonRole)}>
            {ROLES.filter((x) => x !== 'owner').map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </form>
      </Dialog>
      <Dialog open={!!confirm} role="alertdialog" onClose={() => setConfirm(undefined)} title={t('users.disable', { name: confirm?.display_name ?? '' })} description={t('users.disable.confirm', { name: confirm?.display_name ?? '' })} actions={<><Button variant="ghost" onClick={() => setConfirm(undefined)}>{t('common.cancel')}</Button><Button variant="danger" onClick={() => { const u = confirm; setConfirm(undefined); if (u) void run(async () => { await api.disableUser(u.id); await users.reload(); }, t('users.disable', { name: u.display_name })); }}>Disable</Button></>} />
      <Dialog open={!!replace} role="alertdialog" onClose={() => setReplace(undefined)} title={t('users.invite.reset', { name: replace?.display_name ?? '' })} description={t('users.invite.replaceWarning')}
        actions={<><Button variant="ghost" onClick={() => setReplace(undefined)}>{t('common.cancel')}</Button><Button variant="danger" busy={busy} onClick={() => {
          const request = api.reissueInvite;
          if (replace && request) void whileBusy(() => run(async () => {
            const result = await request.call(api, replace.id);
            setReplace(undefined);
            void hub.actions.reload();
            navigate(href.approval(result.id));
          }, t('users.invite.replace')));
        }}>{t('users.invite.replace')}</Button></>} />
      <InviteDialog invite={invite} onClose={() => setInvite(undefined)} />
    </div>
  );
}

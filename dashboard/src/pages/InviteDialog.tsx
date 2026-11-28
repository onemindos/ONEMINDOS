// SPDX-License-Identifier: Apache-2.0
import { useId } from 'react';
import { Button, Dialog, QrSvg } from '@onemind/ui';
import type { UserCreated } from '../api/wiring';
import { t } from '../i18n';

/** The one-time invitation stays in the caller's component state until the owner closes it. */
export function InviteDialog({ invite, onClose }: { invite?: UserCreated; onClose: () => void }) {
  const linkId = useId();
  return <Dialog open={!!invite} onClose={onClose} title={t('users.add')} description={t('users.invite.done', { name: invite?.display_name ?? '' })}
    actions={<Button onClick={onClose}>{t('common.close')}</Button>}>
    {invite && <div className="dash-invite">
      <QrSvg text={invite.one_time.enrolment_url} label={t('users.invite.qr')} />
      <label htmlFor={linkId}>{t('users.invite.link')}</label>
      <input id={linkId} readOnly value={invite.one_time.enrolment_url} onFocus={(e) => e.target.select()} />
      <code className="dash-secret">{invite.one_time.enrolment_code}</code>
      {invite.one_time.expires_at && <p className="om-hint">{t('users.invite.expiry', { expires: new Date(invite.one_time.expires_at).toLocaleString() })}</p>}
    </div>}
  </Dialog>;
}

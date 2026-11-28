// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { Button } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import { ApiError } from '../api/types';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { IdentityFactors } from './IdentityFactors';
import { RecoveryKit } from './RecoveryKit';
import { SignInCard } from './SignIn';
import { useBusy } from './parts';

export function IdentitySetup({ owner, onDone }: { owner: boolean; onDone: () => void }) {
  const { api, signOut } = useSignedIn();
  const me = usePoll(() => api.me(), 0);
  const [busy, run] = useBusy();
  const [kit, setKit] = useState<components['schemas']['SetupKit']>();
  const [error, setError] = useState<string>();
  const attempt = (job: () => Promise<void>) => void run(async () => {
    setError(undefined);
    try { await job(); }
    catch (e) { setError(e instanceof Error ? e.message : t('setup.couldNotFinish')); }
  });
  const finish = (method: components['schemas']['SetupFinishBody']['method']) => attempt(async () => {
    if (!api.finishSetup || !kit) return;
    try { await api.finishSetup({ saved: true, method, recovery_code: kit.recovery_code }); }
    catch (e) {
      if (!(e instanceof ApiError)) throw e;
      if (e.reason === 'recovery_kit_required' || e.reason === 'setup_kit_changed') {
        setKit(undefined);
        throw new Error(t('kit.changed'));
      }
      if (e.reason !== 'setup_not_pending') throw e;
    }
    setKit(undefined);
    onDone();
  });

  return <SignInCard>
    <h1>{owner ? t('setup.identity.title') : t('enrol.identity.title')}</h1>
    {kit ? <RecoveryKit kit={kit} busy={busy} onSaved={finish} /> : <>
      <p className="om-hint">{t('factors.optional')}</p>
      <IdentityFactors api={api} offerEmail offerPasskey email={me.data?.email} emailVerified={me.data?.email_verified} totp={me.data?.totp} reload={me.reload} />
      {owner ? <>
        <p className="om-note om-tone-warn">{t('kit.required')}</p>
        <Button variant="primary" disabled={busy} onClick={() => attempt(async () => { setKit(await api.setupKit?.()); })}>{t('kit.continue')}</Button>
      </> : <Button variant="primary" onClick={onDone}>{t('enrol.identity.done')}</Button>}
    </>}
    <Button variant="ghost" disabled={busy} onClick={signOut}>{t('account.signout')}</Button>
    {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
  </SignInCard>;
}

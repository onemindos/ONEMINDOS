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
import { TextField, useBusy } from './parts';

type FinishBody = components['schemas']['SetupFinishBody'];

export function IdentitySetup({ owner, onDone }: { owner: boolean; onDone: () => void }) {
  const { api, signOut } = useSignedIn();
  const me = usePoll(() => api.me(), 0);
  const [busy, run] = useBusy();
  const [kit, setKit] = useState<components['schemas']['SetupKit']>();
  const [error, setError] = useState<string>();
  const [useSavedKit, setUseSavedKit] = useState(false);
  const [accountCode, setAccountCode] = useState('');
  const [diskKey, setDiskKey] = useState('');
  const [savedMethod, setSavedMethod] = useState<FinishBody['method']>('download');
  const attempt = (job: () => Promise<void>) => void run(async () => {
    setError(undefined);
    try { await job(); }
    catch (e) {
      if (e instanceof ApiError && e.reason === 'disk_recovery_key_missing') {
        setKit(undefined);
        setUseSavedKit(true);
      }
      setError(e instanceof Error ? e.message : t('setup.couldNotFinish'));
    }
  });
  const finish = (body: FinishBody) => attempt(async () => {
    if (!api.finishSetup) return;
    try { await api.finishSetup(body); }
    catch (e) {
      if (!(e instanceof ApiError)) throw e;
      if (e.reason === 'recovery_kit_required' || e.reason === 'setup_kit_changed') {
        if (useSavedKit) throw new Error(t('kit.savedMismatch'));
        setKit(undefined);
        throw new Error(t('kit.changed'));
      }
      if (e.reason !== 'setup_not_pending') throw e;
    }
    setKit(undefined);
    setAccountCode('');
    setDiskKey('');
    onDone();
  });
  const loadKit = () => attempt(async () => {
    setKit(await api.setupKit?.());
    setUseSavedKit(false);
    setAccountCode('');
    setDiskKey('');
  });

  return <SignInCard>
    <h1>{owner ? t('setup.identity.title') : t('enrol.identity.title')}</h1>
    {kit ? <RecoveryKit kit={kit} busy={busy}
      onSaved={(method) => finish({ saved: true, method, recovery_code: kit.recovery_code })} /> : useSavedKit ? <>
      <form className="dash-signin-form" onSubmit={(event) => {
        event.preventDefault();
        if (!busy && accountCode.trim() && diskKey.trim()) finish({
          saved: true, method: savedMethod, recovery_code: accountCode.trim(), disk_recovery_key: diskKey.trim(),
        });
      }}>
        <p className="om-hint">{t('kit.verifySaved')}</p>
        <TextField id="saved-account-code" label={t('kit.code')} type="password" value={accountCode} onChange={setAccountCode} />
        <TextField id="saved-disk-key" label={t('kit.diskKey')} type="password" value={diskKey} onChange={setDiskKey} />
        <label>{t('kit.savedMethod')}{' '}
          <select value={savedMethod} onChange={(event) => setSavedMethod(event.target.value === 'print' ? 'print' : 'download')}>
            <option value="download">{t('kit.savedDownload')}</option>
            <option value="print">{t('kit.savedPrint')}</option>
          </select>
        </label>
        <Button type="submit" variant="primary" disabled={busy || !accountCode.trim() || !diskKey.trim()}>{t('kit.confirmSaved')}</Button>
      </form>
      <Button variant="ghost" disabled={busy} onClick={loadKit}>{t('kit.continue')}</Button>
    </> : <>
      <p className="om-hint">{t('factors.optional')}</p>
      <IdentityFactors api={api} offerEmail offerPasskey email={me.data?.email} emailVerified={me.data?.email_verified} totp={me.data?.totp} reload={me.reload} />
      {owner ? <>
        <p className="om-note om-tone-warn">{t('kit.required')}</p>
        <Button variant="primary" disabled={busy} onClick={loadKit}>{t('kit.continue')}</Button>
      </> : <Button variant="primary" onClick={onDone}>{t('enrol.identity.done')}</Button>}
    </>}
    <Button variant="ghost" disabled={busy} onClick={signOut}>{t('account.signout')}</Button>
    {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
  </SignInCard>;
}

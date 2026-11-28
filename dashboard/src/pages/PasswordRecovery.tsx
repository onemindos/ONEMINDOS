// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from 'react';
import { Button } from '@onemind/ui';
import type { WiringApi } from '../api/wiring';
import { t } from '../i18n';
import { RecoveryKit } from './RecoveryKit';
import { TextField, useBusy } from './parts';

export function PasswordRecovery({ api, onBack }: { api: WiringApi; onBack: () => void }) {
  const [busy, run] = useBusy();
  const [username, setUsername] = useState('');
  const [challengeId, setChallengeId] = useState<string>();
  const [boxCode, setBoxCode] = useState('');
  const [kitCode, setKitCode] = useState('');
  const [password, setPassword] = useState('');
  const [replacement, setReplacement] = useState<string>();
  const [error, setError] = useState<string>();

  const attempt = (job: () => Promise<void>) => void run(async () => {
    setError(undefined);
    try { await job(); }
    catch (e) { setError(e instanceof Error ? e.message : t('recovery.failed')); }
  });
  const showCode = (e: FormEvent) => {
    e.preventDefault();
    if (!api.recoveryOptions || !username.trim()) return;
    attempt(async () => {
      const result = await api.recoveryOptions?.({ username: username.trim() });
      setChallengeId(result?.challenge_id);
      setBoxCode('');
    });
  };
  const reset = (e: FormEvent) => {
    e.preventDefault();
    if (!api.resetPasswordAtBox || !challengeId || !/^\d{6}$/.test(boxCode) || !kitCode.trim()) return;
    if ([...password].length < 12) { setError(t('setup.short')); return; }
    attempt(async () => {
      try {
        const result = await api.resetPasswordAtBox?.({ challenge_id: challengeId, box_code: boxCode, recovery_code: kitCode.trim(), new_password: password });
        setReplacement(result?.recovery_code);
      } finally {
        setChallengeId(undefined);
        setBoxCode('');
        setKitCode('');
        setPassword('');
      }
    });
  };
  return <>
    <h1>{replacement ? t('recovery.done') : t('recovery.title')}</h1>
    {replacement ? <>
      <p>{t('recovery.replace')}</p>
      <RecoveryKit kit={{ recovery_code: replacement, disk_recovery_key: null }} busy={false} onSaved={onBack} />
    </> : <>
      <p className="om-hint">{t('recovery.lede')}</p>
      <p className="om-hint">{t('recovery.remote')}</p>
      {challengeId ? <form className="dash-signin-form" onSubmit={reset} noValidate>
        <label htmlFor="reset-box-code">{t('setup.boxCode')}</label>
        <input id="reset-box-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={boxCode} onChange={(e) => setBoxCode(e.target.value)} />
        <TextField id="reset-kit-code" label={t('kit.code')} type="password" value={kitCode} onChange={setKitCode} />
        <TextField id="reset-new-password" label={t('setup.password')} type="password" autoComplete="new-password" value={password} onChange={setPassword} />
        <Button type="submit" variant="primary" disabled={busy || !/^\d{6}$/.test(boxCode) || !kitCode.trim()}>{t('recovery.reset')}</Button>
        <Button type="button" variant="ghost" disabled={busy} onClick={showCode}>{t('setup.newCode')}</Button>
      </form> : <form className="dash-signin-form" onSubmit={showCode}>
        <TextField id="reset-username" label={t('signin.username')} value={username} autoComplete="username" onChange={setUsername} />
        <Button type="submit" variant="primary" disabled={busy || !username.trim()}>{t('setup.showCode')}</Button>
      </form>}
      {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
      <Button variant="ghost" onClick={onBack} disabled={busy}>{t('signin.back')}</Button>
    </>}
  </>;
}

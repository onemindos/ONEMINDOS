// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent } from 'react';
import { Button, QrSvg } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import type { WiringApi } from '../api/wiring';
import { t } from '../i18n';
import { registerPasskey } from '../lib/registerPasskey';
import { webauthnSupported } from '../lib/webauthn';
import { TextField, useBusy } from './parts';

export function IdentityFactors({ api, totp, email, emailVerified, offerEmail, offerPasskey, reload }: {
  api: WiringApi;
  totp?: boolean;
  email?: string | null;
  emailVerified?: boolean;
  offerEmail?: boolean;
  offerPasskey?: boolean;
  reload?: () => Promise<unknown>;
}) {
  const [busy, run] = useBusy();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [pending, setPending] = useState<components['schemas']['TotpSetup']['one_time']>();
  const [code, setCode] = useState('');
  const [totpChanged, setTotpChanged] = useState<boolean>();
  const [passkeyAdded, setPasskeyAdded] = useState(false);
  const [editingEmail, setEditingEmail] = useState(false);
  const [emailDraft, setEmailDraft] = useState('');
  const [emailChallenge, setEmailChallenge] = useState<string>();
  const [emailCode, setEmailCode] = useState('');
  const [turningOff, setTurningOff] = useState(false);
  const [password, setPassword] = useState('');
  const attempt = (fn: () => Promise<unknown>) => void run(async () => {
    setError(undefined);
    setNotice(undefined);
    try { await fn(); }
    catch (e) { setError(e instanceof Error ? e.message : t('factors.failed')); }
  });
  const confirm = (e: FormEvent) => {
    e.preventDefault();
    if (!api.confirmTotp) return;
    attempt(async () => {
      await api.confirmTotp?.({ code });
      setPending(undefined);
      setCode('');
      setTotpChanged(true);
      setNotice(t('factors.authenticator.added'));
      await reload?.();
    });
  };
  const active = totpChanged ?? totp;
  return (
    <div className="dash-identity-factors">
      {offerEmail && api.updateIdentityEmail && <section>
        <h3>{t('factors.email')}</h3>
        <p className="om-hint">{email ? (emailVerified ? t('factors.email.verified', { email }) : t('factors.email.unverified', { email })) : t('factors.email.why')}</p>
        {editingEmail ? (
          <form className="dash-form" onSubmit={(e) => {
            e.preventDefault();
            attempt(async () => {
              await api.updateIdentityEmail?.(emailDraft.trim() || null);
              setEditingEmail(false);
              setEmailDraft('');
              setNotice(t('factors.email.saved'));
              await reload?.();
            });
          }}>
            <TextField id="identity-email" label={t('factors.email')} type="email" autoComplete="email" value={emailDraft} onChange={setEmailDraft} />
            <div className="dash-identity-actions">
              <Button type="submit" disabled={busy}>{t('factors.email.save')}</Button>
              <Button type="button" variant="ghost" onClick={() => setEditingEmail(false)}>{t('common.cancel')}</Button>
            </div>
          </form>
        ) : <Button onClick={() => { setEditingEmail(true); setEmailDraft(email ?? ''); setEmailChallenge(undefined); setEmailCode(''); }} disabled={busy}>{email ? t('factors.email.change') : t('factors.email.add')}</Button>}
        {!editingEmail && email && !emailVerified && api.emailOptions && api.verifyIdentityEmail && (emailChallenge ? (
          <form className="dash-form" onSubmit={(e) => {
            e.preventDefault();
            attempt(async () => {
              try {
                await api.verifyIdentityEmail?.({ challenge_id: emailChallenge, code: emailCode });
                setNotice(t('factors.email.done'));
                await reload?.();
              } finally { setEmailChallenge(undefined); setEmailCode(''); }
            });
          }}>
            <label htmlFor="identity-email-code">{t('factors.email.code')}</label>
            <input id="identity-email-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={emailCode} onChange={(e) => setEmailCode(e.target.value)} />
            <div className="dash-identity-actions">
              <Button type="submit" disabled={busy || !/^\d{6}$/.test(emailCode)}>{t('factors.email.verify')}</Button>
              <Button type="button" variant="ghost" onClick={() => { setEmailChallenge(undefined); setEmailCode(''); }}>{t('common.cancel')}</Button>
            </div>
          </form>
        ) : <Button variant="ghost" disabled={busy} onClick={() => attempt(async () => {
          const answer = await api.emailOptions?.();
          setEmailChallenge(answer?.challenge_id);
        })}>{t('factors.email.send')}</Button>)}
      </section>}
      {api.setupTotp && api.confirmTotp && <section>
        <h3>{t('factors.authenticator')}</h3>
        {pending ? (
          <form className="dash-form" onSubmit={confirm}>
            <p>{t('factors.authenticator.scan')}</p>
            <QrSvg text={pending.otpauth_uri} label={t('factors.authenticator.qr')} />
            <p>{t('factors.authenticator.manual')} <code className="dash-secret">{pending.secret}</code></p>
            <label htmlFor="authenticator-code">{t('factors.authenticator.code')}</label>
            <input id="authenticator-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />
            <div className="dash-identity-actions">
              <Button type="submit" disabled={busy || !/^\d{6}$/.test(code)}>{t('factors.authenticator.confirm')}</Button>
              <Button type="button" variant="ghost" onClick={() => { setPending(undefined); setCode(''); }}>{t('common.cancel')}</Button>
            </div>
          </form>
        ) : active ? (
          <>
            <p className="om-hint">{t('factors.authenticator.enabled')}</p>
            {api.disableTotp && (turningOff ? <form className="dash-form" onSubmit={(e) => {
              e.preventDefault();
              attempt(async () => {
                await api.disableTotp?.({ password });
                setTotpChanged(false);
                setTurningOff(false);
                setPassword('');
                await reload?.();
              });
            }}>
              <TextField id="disable-auth-password" label={t('signin.password')} type="password" autoComplete="current-password" value={password} onChange={setPassword} />
              <div className="dash-identity-actions">
                <Button type="submit" variant="danger" disabled={busy || !password}>{t('factors.authenticator.turnOff')}</Button>
                <Button type="button" variant="ghost" onClick={() => { setTurningOff(false); setPassword(''); }}>{t('common.cancel')}</Button>
              </div>
            </form> : <Button variant="ghost" onClick={() => setTurningOff(true)}>{t('factors.authenticator.turnOff')}</Button>)}
          </>
        ) : <Button disabled={busy} onClick={() => attempt(async () => {
          const answer = await api.setupTotp?.();
          if (answer) setPending(answer.one_time);
        })}>{t('factors.authenticator.add')}</Button>}
      </section>}
      {offerPasskey && <section>
        <h3>{t('account.passkeys')}</h3>
        {passkeyAdded ? <p>{t('account.passkeys.added')}</p> : webauthnSupported() ? <Button disabled={busy} onClick={() => attempt(async () => {
          await registerPasskey(api);
          setPasskeyAdded(true);
        })}>{t('account.passkeys.add')}</Button> : <p className="om-hint">{t('account.passkeys.unsupported')}</p>}
      </section>}
      {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
      {notice && <p className="om-hint" role="status">{notice}</p>}
    </div>
  );
}

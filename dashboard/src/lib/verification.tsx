// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Dialog } from '@onemind/ui';
import type { StepUpVerification } from '@onemind/sdk';
import { ApiError } from '../api/types';
import { t } from '../i18n';
import { boxCodeWhat } from './boxcode';
import { webauthnSupported } from './webauthn';

type Request = Parameters<StepUpVerification>[0];
type Verification = Awaited<ReturnType<StepUpVerification>>;
type Pending = { request: Request; allowPassword: boolean; resolve: (value: Verification) => void; reject: (error: ApiError) => void };
let show: ((ask: Pending) => void) | undefined;

const cancelled = () => new ApiError(400, 'unknown', 'Verification cancelled.', 'cancelled');

export async function chooseVerification(request: Request, allowPassword: boolean): Promise<Verification> {
  if (!show || request.required_level === 'L3' || (request.required_level === 'L2' && !request.box)) return { method: 'passkey' };
  return new Promise((resolve, reject) => show?.({ request, allowPassword, resolve, reject }));
}

export const askVerification: StepUpVerification = (request) => chooseVerification(request, true);

export function VerificationHost() {
  const [ask, setAsk] = useState<Pending>();
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const pending = useRef<Pending | undefined>(undefined);
  useEffect(() => {
    show = (value) => {
      pending.current?.reject(cancelled());
      pending.current = value;
      setPassword('');
      setTotp('');
      setAsk(value);
    };
    return () => { show = undefined; pending.current?.reject(cancelled()); };
  }, []);
  if (!ask) return null;
  const passkey = webauthnSupported();
  const box = ask.request.box;
  const done = (value?: Verification) => {
    pending.current = undefined;
    setAsk(undefined);
    setPassword('');
    setTotp('');
    if (value) ask.resolve(value);
    else ask.reject(cancelled());
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (password && /^\d{6}$/.test(totp)) done({ method: 'password+totp', password, totp, atBox: box === 'alt' });
  };
  return <Dialog open onClose={() => done()} title={t('verify.title')} size="sm"
    description={t('verify.what', { what: boxCodeWhat(ask.request.op) })}
    actions={<Button variant="ghost" onClick={() => done()}>{t('common.cancel')}</Button>}>
    <div className="dash-form">
      {passkey && <div className="dash-identity-actions">
        <Button onClick={() => done({ method: 'passkey' })}>{t('signin.passkey')}</Button>
        {box === 'alt' && <Button onClick={() => done({ method: 'passkey', atBox: true })}>{t('verify.passkeyAtBox')}</Button>}
      </div>}
      {box && ask.allowPassword && <p className="om-hint">{t('verify.box')}</p>}
      {!passkey && !ask.allowPassword && <p className="om-hint">{t('account.passkeys.unsupported')}</p>}
      {box && !ask.allowPassword && <p className="om-hint">{t('verify.addAuthenticator')}</p>}
      {ask.allowPassword && <form className="dash-form" onSubmit={submit}>
        <label htmlFor="verify-password">{t('signin.password')}</label>
        <input id="verify-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <label htmlFor="verify-totp">{t('factors.authenticator.code')}</label>
        <input id="verify-totp" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value)} />
        <Button type="submit" variant="primary" disabled={!password || !/^\d{6}$/.test(totp)}>{t('verify.confirm')}</Button>
      </form>}
    </div>
  </Dialog>;
}

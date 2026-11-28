// SPDX-License-Identifier: Apache-2.0
// Settings > Account and security: your password and the authenticator code (TOTP), M1 of the UI parity report.
// Reads GET /v1/auth/methods; changes go to POST /v1/auth/password and /v1/auth/totp/{setup,confirm,disable}
// through @onemind/sdk. These are your own sign-in credentials: the gateway asks for a signed-in session (never an
// API token), checks the current password and audits every change; this screen adds no check of its own.
// D-034 (amends D-030 point 2): a person signs in with a password, a password and an authenticator code, or a passkey;
// passkeys are recommended, and this card never asks a passkey user to add an authenticator code.
import { useState, type FormEvent } from 'react';
import type { components } from '@onemind/sdk';
import { Button, Card, QrSvg, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useGateway, viaSdk } from '../lib/gateway';
import { usePoll, type Polled } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load } from './parts';

type Methods = components['schemas']['SignInMethods'];
type Secret = components['schemas']['TotpSecret'];

/** The gateway's refusal in words a first-time owner can act on. */
export function signInError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.reason === 'bad_credentials') return 'That password is not right. Nothing was changed.';
    if (e.reason === 'weak_password') return 'The new password must be at least 12 characters long.';
    if (e.reason === 'totp_invalid') return 'That code does not match. Type the 6 digits your app shows now; if it keeps failing, check the time on your phone.';
    if (e.reason === 'session_required') return 'This needs you to be signed in on this device. Sign out, sign in again and try once more.';
    if (e.status === 429) return 'Too many tries. Wait a minute, then try again.';
    if (e.status === 409) return e.message.charAt(0).toUpperCase() + e.message.slice(1) + '.';
    if (e.code === 'network') return 'The box did not answer. Nothing was changed; try again.';
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export function AccountSignIn() {
  const { token, mock } = useSignedIn();
  if (mock) return <Card title="Password and authenticator code"><p role="status">Connect to a real box to change your password or authenticator code. Demo mode has no real account.</p></Card>;
  return <LiveSignIn token={token} />;
}

function LiveSignIn({ token }: { token: string }) {
  const sdk = useGateway(token);
  const methods = usePoll(() => viaSdk(() => sdk.call<Methods>({ method: 'GET', path: '/v1/auth/methods' })), 0);
  return (
    <Load res={methods} what="Loading how you sign in">
      {(m) => (
        <>
          {m.password && <PasswordCard sdk={sdk} />}
          <AuthenticatorCard sdk={sdk} methods={m} reload={methods.reload} />
        </>
      )}
    </Load>
  );
}

type Sdk = ReturnType<typeof useGateway>;

function useJob() {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string>();
  const run = async (job: () => Promise<void>) => {
    setBusy(true);
    setFailed(undefined);
    try {
      await job();
    } catch (e) {
      setFailed(signInError(e));
    } finally {
      setBusy(false);
    }
  };
  return { busy, failed, run };
}

function PasswordCard({ sdk }: { sdk: Sdk }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [done, setDone] = useState(false);
  const { busy, failed, run } = useJob();
  const mismatch = again.length > 0 && next !== again;
  const ready = current.length > 0 && [...next].length >= 12 && next === again;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      setDone(false);
      await viaSdk(() => sdk.call<void>({ method: 'POST', path: '/v1/auth/password', body: { current_password: current, new_password: next } }));
      setCurrent('');
      setNext('');
      setAgain('');
      setDone(true);
    });
  };
  return (
    <Card title="Password" subtitle="Used when you sign in without a passkey">
      <p>Changing your password signs you out on every other device. You stay signed in here.</p>
      {failed && <p className="om-note om-tone-bad" role="alert">{failed}</p>}
      {done && <p className="om-note om-tone-ok" role="status">Your password is changed. Other devices were signed out.</p>}
      <form className="dash-form" onSubmit={submit} aria-label="Change your password">
        <label htmlFor="pw-current">Current password</label>
        <input id="pw-current" type="password" autoComplete="current-password" value={current} maxLength={1024} onChange={(e) => setCurrent(e.target.value)} />
        <label htmlFor="pw-new">New password</label>
        <input id="pw-new" type="password" autoComplete="new-password" value={next} maxLength={1024} aria-describedby="pw-new-hint" onChange={(e) => setNext(e.target.value)} />
        <span id="pw-new-hint" className="om-hint">At least 12 characters; spaces are fine. A few unrelated words are easy to remember and hard to guess.</span>
        <label htmlFor="pw-again">New password again</label>
        <input id="pw-again" type="password" autoComplete="new-password" value={again} maxLength={1024} aria-invalid={mismatch} aria-describedby={mismatch ? 'pw-again-hint' : undefined} onChange={(e) => setAgain(e.target.value)} />
        {mismatch && <span id="pw-again-hint" className="om-hint om-tone-bad">The two new passwords are not the same.</span>}
        <Button type="submit" disabled={busy || !ready}>{busy ? 'Changing…' : 'Change password'}</Button>
      </form>
    </Card>
  );
}

function AuthenticatorCard({ sdk, methods, reload }: { sdk: Sdk; methods: Methods; reload: Polled<Methods>['reload'] }) {
  const [secret, setSecret] = useState<Secret>();
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [turningOff, setTurningOff] = useState(false);
  const [note, setNote] = useState<string>();
  const { busy, failed, run } = useJob();

  const start = () => void run(async () => {
    setNote(undefined);
    const r = await viaSdk(() => sdk.call<components['schemas']['TotpSetup']>({ method: 'POST', path: '/v1/auth/totp/setup' }));
    setSecret(r.one_time);
  });
  const confirm = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await viaSdk(() => sdk.call<void>({ method: 'POST', path: '/v1/auth/totp/confirm', body: { code: code.trim() } }));
      setSecret(undefined);
      setCode('');
      setNote('The authenticator code is on. The box asks for it after your password.');
      await reload();
    });
  };
  const disable = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await viaSdk(() => sdk.call<void>({ method: 'POST', path: '/v1/auth/totp/disable', body: { password } }));
      setPassword('');
      setTurningOff(false);
      setNote('The authenticator code is off.');
      await reload();
    });
  };

  const pill = methods.totp ? <StatusPill tone="ok" label="On" /> : <StatusPill tone="neutral" label="Off" />;
  return (
    <Card title="Authenticator code" subtitle="A fallback for password sign-in" aside={pill}>
      <p>
        Passkeys are recommended. You can also sign in with a password, alone or with an authenticator code (a 6-digit number from an app such as
        Google Authenticator or 1Password) that the box asks for after the password. From outside your home, sign-in needs that code or a passkey.
      </p>
      {failed && <p className="om-note om-tone-bad" role="alert">{failed}</p>}
      {note && <p className="om-note om-tone-ok" role="status">{note}</p>}
      {methods.totp ? (
        turningOff ? (
          <form className="dash-form" onSubmit={disable} aria-label="Turn off the authenticator code">
            <label htmlFor="totp-off-password">Your password</label>
            <input id="totp-off-password" type="password" autoComplete="current-password" value={password} maxLength={1024} onChange={(e) => setPassword(e.target.value)} />
            <div className="dash-actions">
              <Button type="submit" variant="danger" disabled={busy || !password}>Turn off</Button>
              <Button type="button" variant="ghost" onClick={() => { setTurningOff(false); setPassword(''); }}>Keep it on</Button>
            </div>
          </form>
        ) : (
          <Button variant="ghost" onClick={() => setTurningOff(true)}>Turn off the authenticator code</Button>
        )
      ) : !methods.password ? (
        <p className="om-hint">You sign in with a passkey and have no password, so an authenticator code would never be asked. There is nothing to set up.</p>
      ) : secret ? (
        <form className="dash-form" onSubmit={confirm} aria-label="Confirm the authenticator code">
          <p>Scan this code with your authenticator app, or type the key by hand. It is shown once.</p>
          <QrSvg text={secret.otpauth_uri} label="QR code for your authenticator app" />
          <span>Key, if you type it by hand:</span>
          <code className="dash-secret">{secret.secret}</code>
          <label htmlFor="totp-code">The 6-digit code your app shows</label>
          <input id="totp-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          <div className="dash-actions">
            <Button type="submit" disabled={busy || code.length !== 6}>Turn on</Button>
            <Button type="button" variant="ghost" onClick={() => { setSecret(undefined); setCode(''); }}>Cancel</Button>
          </div>
        </form>
      ) : methods.passkeys > 0 ? (
        <details>
          <summary>You sign in with a passkey, so you do not need this. Set one up anyway</summary>
          <p className="om-hint">Only useful if you also sign in with your password somewhere a passkey does not work.</p>
          <Button variant="ghost" disabled={busy} onClick={start}>Set up an authenticator code</Button>
        </details>
      ) : (
        <>
          <p className="om-hint">The safer step is a passkey: add one under Passkeys on this page. Use an authenticator code only if you keep signing in with your password.</p>
          <Button variant="ghost" disabled={busy} onClick={start}>Set up an authenticator code</Button>
        </>
      )}
    </Card>
  );
}

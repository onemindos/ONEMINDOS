// SPDX-License-Identifier: Apache-2.0
// Sign-in: passkey, account (username + password + optional authenticator code), or the access
// token of contract §3. Also the two ways a person first gets an account: the owner's first-run
// setup (POST /v1/auth/setup) and an invite code (POST /v1/auth/enrol). Every path ends in a
// bearer access token held in sessionStorage only (session.tsx); nothing goes to localStorage.
// One error line at a time (role=alert) so a screen reader hears exactly one message.
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { BrandMark, Button } from '@onemind/ui';
import { ApiError } from '../api/types';
import type { LoginResult } from '../api/wiring';
import { brand } from '../brand.generated';
import { t } from '../i18n';
import { getPasskey, webauthnSupported } from '../lib/webauthn';
import { useSession } from '../session';

/** Set after a first-run setup so the signed-in app opens the wizard once (cleared by it). */
export const WIZARD_KEY = 'onemind.wizard';

type View = 'signin' | 'setup' | 'enrol';

function Field(props: { label: string; name: string; type?: string; value: string; onChange: (v: string) => void; autoComplete?: string; describedBy?: string; invalid?: boolean }) {
  return (
    <>
      <label htmlFor={props.name}>{props.label}</label>
      <input
        id={props.name}
        name={props.name}
        type={props.type ?? 'text'}
        autoComplete={props.autoComplete}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        aria-invalid={props.invalid ? true : undefined}
        aria-describedby={props.describedBy}
      />
    </>
  );
}

function initialView(): View {
  try {
    if (window.location.hash.includes('enrol=')) return 'enrol';
  } catch {
    /* no window.location in odd test setups */
  }
  return 'signin';
}
function hashCode(): string {
  try {
    return decodeURIComponent(/enrol=([^&]*)/.exec(window.location.hash)?.[1] ?? '');
  } catch {
    return '';
  }
}

export function SignIn({ mock }: { mock: boolean }) {
  const { signIn, anon } = useSession();
  const [view, setView] = useState<View>(initialView);
  const [error, setError] = useState<string>();
  const [errorFor, setErrorFor] = useState<string>();
  const [busy, setBusy] = useState(false);
  const errId = useId();
  const hintId = useId();
  const [token, setToken] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [setupToken, setSetupToken] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [code, setCode] = useState(hashCode);

  const fail = (field: string, msg: string) => {
    setError(msg);
    setErrorFor(field);
  };
  const unreachable = (err: unknown) => t('signin.unreachable', { detail: err instanceof Error && !(err instanceof ApiError && err.status > 0) ? ` (${err.message})` : '' });

  async function run(field: string, job: () => Promise<void>, onApi: (e: ApiError) => string) {
    setBusy(true);
    setError(undefined);
    try {
      await job();
    } catch (err) {
      if (err instanceof ApiError && err.code !== 'network') fail(field, onApi(err));
      else fail(field, unreachable(err));
    } finally {
      setBusy(false);
    }
  }
  const finish = (r: LoginResult, wizard = false) => {
    if (wizard) {
      try {
        window.sessionStorage.setItem(WIZARD_KEY, '1');
      } catch {
        /* the wizard is then simply skipped */
      }
    }
    return signIn(r.access_token);
  };

  const onToken = (e: FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return fail('token', t('signin.token.empty'));
    void run('token', () => signIn(token), (er) => (er.code === 'unauthenticated' ? t('signin.token.bad') : unreachable(er)));
  };
  const onAccount = (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return fail('username', t('signin.account.empty'));
    void run('username', async () => finish(await anon.loginPassword({ username: username.trim(), password, ...(totp.trim() ? { totp: totp.trim() } : {}) })), (er) => (er.code === 'unauthenticated' || er.code === 'rate_limited' ? (er.code === 'rate_limited' ? er.message : t('signin.account.bad')) : unreachable(er)));
  };
  const onPasskey = () =>
    void run(
      'passkey',
      async () => {
        const o = await anon.loginOptions();
        const credential = await getPasskey(o.publicKey);
        await finish(await anon.loginPasskey(credential));
      },
      (er) => (er.code === 'unauthenticated' ? t('signin.passkey.bad') : unreachable(er)),
    );
  const onSetup = (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 12) return fail('password', t('setup.short'));
    void run(
      'setup-token',
      async () => finish(await anon.setup(setupToken.trim(), { username: username.trim(), display_name: displayName.trim() || username.trim(), password }), true),
      (er) => (er.status === 409 ? t('setup.done') : er.code === 'unauthenticated' ? t('setup.badToken') : er.message),
    );
  };
  const onEnrol = (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 12) return fail('password', t('setup.short'));
    void run('code', async () => finish(await anon.enrol({ code: code.trim(), username: username.trim() || undefined, password })), (er) => (er.code === 'unauthenticated' || er.code === 'not_found' ? t('enrol.bad') : er.message));
  };

  const describe = (field: string, extra?: string) => [extra ?? '', error && errorFor === field ? errId : ''].filter(Boolean).join(' ') || undefined;
  const bad = (field: string) => !!error && errorFor === field;
  const alert: ReactNode = error && (
    <p id={errId} className="om-note om-tone-bad" role="alert">
      {error}
    </p>
  );
  const go = (v: View) => {
    setView(v);
    setError(undefined);
    setPassword('');
  };

  return (
    <main id="main" className="dash-signin">
      <div className="dash-signin-card">
        <BrandMark className="om-brand-mark dash-signin-mark" />
        {view === 'signin' && (
          <>
            <h1>{t('signin.title', { name: brand.shortName })}</h1>
            <p className="om-hint">{t('signin.lede')}</p>
            {webauthnSupported() ? (
              <Button variant="primary" onClick={onPasskey} disabled={busy}>
                {t('signin.passkey')}
              </Button>
            ) : (
              <p className="om-hint">{t('signin.passkey.unsupported')}</p>
            )}
            <form onSubmit={onAccount} noValidate className="dash-signin-form">
              <h2 className="dash-signin-sub">{t('signin.account.heading')}</h2>
              <Field label={t('signin.username')} name="username" autoComplete="username" value={username} onChange={setUsername} invalid={bad('username')} describedBy={describe('username')} />
              <Field label={t('signin.password')} name="password" type="password" autoComplete="current-password" value={password} onChange={setPassword} />
              <Field label={t('signin.totp')} name="totp" autoComplete="one-time-code" value={totp} onChange={setTotp} />
              <Button type="submit" disabled={busy}>
                {t('signin.account.submit')}
              </Button>
            </form>
            <form onSubmit={onToken} noValidate className="dash-signin-form">
              <h2 className="dash-signin-sub">{t('signin.token.heading')}</h2>
              <Field label={t('signin.token.label')} name="token" type="password" autoComplete="off" value={token} onChange={setToken} invalid={bad('token')} describedBy={describe('token', mock ? hintId : undefined)} />
              {mock && (
                <p id={hintId} className="om-hint">
                  {t('signin.mockHint')}
                </p>
              )}
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? t('signin.busy') : t('signin.token.submit')}
              </Button>
            </form>
            {alert}
            <p className="om-hint">{t('signin.expiry')}</p>
            <p className="dash-signin-links">
              <button type="button" className="om-link" onClick={() => go('setup')}>
                {t('signin.firstTime')}
              </button>
              <button type="button" className="om-link" onClick={() => go('enrol')}>
                {t('signin.haveCode')}
              </button>
            </p>
          </>
        )}
        {view === 'setup' && (
          <>
            <h1>{t('setup.title')}</h1>
            <p className="om-hint">{t('setup.lede')}</p>
            <form onSubmit={onSetup} noValidate className="dash-signin-form">
              <Field label={t('setup.token')} name="setup-token" type="password" autoComplete="off" value={setupToken} onChange={setSetupToken} invalid={bad('setup-token')} describedBy={describe('setup-token')} />
              <Field label={t('setup.username')} name="username" autoComplete="username" value={username} onChange={setUsername} />
              <Field label={t('setup.displayName')} name="display-name" autoComplete="name" value={displayName} onChange={setDisplayName} />
              <Field label={t('setup.password')} name="password" type="password" autoComplete="new-password" value={password} onChange={setPassword} invalid={bad('password')} describedBy={describe('password')} />
              <Button type="submit" variant="primary" disabled={busy}>
                {t('setup.submit')}
              </Button>
            </form>
            {alert}
            <button type="button" className="om-link" onClick={() => go('signin')}>
              {t('signin.back')}
            </button>
          </>
        )}
        {view === 'enrol' && (
          <>
            <h1>{t('enrol.title')}</h1>
            <p className="om-hint">{t('enrol.lede')}</p>
            <form onSubmit={onEnrol} noValidate className="dash-signin-form">
              <Field label={t('enrol.code')} name="code" autoComplete="off" value={code} onChange={setCode} invalid={bad('code')} describedBy={describe('code')} />
              <Field label={t('setup.username')} name="username" autoComplete="username" value={username} onChange={setUsername} />
              <Field label={t('setup.password')} name="password" type="password" autoComplete="new-password" value={password} onChange={setPassword} invalid={bad('password')} describedBy={describe('password')} />
              <Button type="submit" variant="primary" disabled={busy}>
                {t('enrol.submit')}
              </Button>
            </form>
            {alert}
            <button type="button" className="om-link" onClick={() => go('signin')}>
              {t('signin.back')}
            </button>
          </>
        )}
      </div>
    </main>
  );
}

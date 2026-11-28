// SPDX-License-Identifier: Apache-2.0
// Sign-in: passkey, account (username + password + optional authenticator code), or the access
// token of contract §3. Also the two ways a person first gets an account: the owner's first-run
// setup (POST /v1/auth/setup) and an invite code (POST /v1/auth/enrol). Every path ends in a
// bearer access token held in sessionStorage only (session.tsx); nothing goes to localStorage.
// One error line at a time (role=alert) so a screen reader hears exactly one message.
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { BrandMark, Button, WallpaperSurface, wallpaperLayers, DEFAULT_APPEARANCE } from '@onemind/ui';
import { ApiError } from '../api/types';
import type { LoginResult } from '../api/wiring';
import { brand } from '../brand.generated';
import { t } from '../i18n';
import { getPasskey, webauthnSupported } from '../lib/webauthn';
import { useSession } from '../session';
import { TrustThisBox } from './TrustThisBox';

type View = 'signin' | 'setup' | 'enrol';

function Field(props: { label: string; name: string; type?: string; value: string; onChange: (v: string) => void; autoComplete?: string; inputMode?: 'numeric'; describedBy?: string; invalid?: boolean }) {
  return (
    <>
      <label htmlFor={props.name}>{props.label}</label>
      <input
        id={props.name}
        name={props.name}
        type={props.type ?? 'text'}
        autoComplete={props.autoComplete}
        inputMode={props.inputMode}
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

export function SignIn({ mock, lockedBox, onReturnToLock, switchPerson }: {
  mock: boolean; lockedBox?: string; onReturnToLock?: () => void; switchPerson?: boolean;
}) {
  const { signIn, anon } = useSession();
  const [view, setView] = useState<View>(() => lockedBox ? 'signin' : initialView());
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
  const [chipGone, setChipGone] = useState(false);
  // The box's own name, read before sign-in (GET /v1/instance/name). Until it arrives, or if the
  // hub is unreachable, the product name stands in: the page never waits on it.
  const [boxName, setBoxName] = useState<string>();
  useEffect(() => {
    if (lockedBox) return;
    let live = true;
    void anon.instanceName?.().then(
      (r) => live && setBoxName(r.name),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [anon, lockedBox]);
  const passkeyOk = webauthnSupported();
  const layers = wallpaperLayers(lockedBox ? 'contour' : DEFAULT_APPEARANCE.wallpaper, null);

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
  // Whether the first-run wizard opens is the gateway's call (/v1/onboarding/state), not a browser flag.
  const finish = (r: LoginResult) => signIn(r.access_token);

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
      async () => finish(await anon.setup(setupToken.trim(), { username: username.trim(), display_name: displayName.trim() || username.trim(), password })),
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
      {layers && <WallpaperSurface layers={layers} className="dash-signin-wp" />}
      <div className="dash-signin-card">
        <BrandMark className="om-brand-mark dash-signin-mark" />
        {view === 'signin' && (
          <>
            <h1>{lockedBox ? (switchPerson ? t('lock.switchPerson') : t('lock.unlockTitle', { name: lockedBox })) : t('signin.title', { name: boxName || brand.shortName })}</h1>
            <p className="om-hint">{t('signin.lede')}</p>
            {mock && !lockedBox && !chipGone && (
              <p id={hintId} className="dash-chip">
                <span>{t('signin.mockHint')}</span>
                <button type="button" className="dash-chip-x" aria-label={t('signin.mockHint.dismiss')} onClick={() => setChipGone(true)}>
                  <span aria-hidden="true">×</span>
                </button>
              </p>
            )}
            {!lockedBox && <TrustThisBox />}
            {passkeyOk ? (
              <Button variant="primary" onClick={onPasskey} disabled={busy}>
                {t('signin.passkey')}
              </Button>
            ) : (
              <p className="om-hint">{(lockedBox ? t('lock.passwordFallback') : t('signin.passkey.unsupported'))}</p>
            )}
            {/* D-034: passkeys are optional, so the password (and authenticator code) form is a first choice too. */}
            {passkeyOk && <p className="dash-signin-or" aria-hidden="true"><span>{t('signin.or')}</span></p>}
            <form onSubmit={onAccount} noValidate className="dash-signin-form">
              <h2 className="dash-signin-sub">{t('signin.account.heading')}</h2>
              <Field label={t('signin.username')} name="username" autoComplete="username" value={username} onChange={setUsername} invalid={bad('username')} describedBy={describe('username')} />
              <Field label={t('signin.password')} name="password" type="password" autoComplete="current-password" value={password} onChange={setPassword} />
              <Field label={t('signin.totp')} name="totp" autoComplete="one-time-code" inputMode="numeric" value={totp} onChange={setTotp} />
              <Button type="submit" disabled={busy}>
                {t('signin.account.submit')}
              </Button>
            </form>
            <details className="dash-signin-more" open={!passkeyOk || undefined}>
              <summary>{t('signin.more')}</summary>
              <form onSubmit={onToken} noValidate className="dash-signin-form">
                <h2 className="dash-signin-sub">{t('signin.token.heading')}</h2>
                <Field label={t('signin.token.label')} name="token" type="password" autoComplete="off" value={token} onChange={setToken} invalid={bad('token')} describedBy={describe('token', mock && !lockedBox && !chipGone ? hintId : undefined)} />
                <Button type="submit" variant="primary" disabled={busy}>
                  {busy ? t('signin.busy') : t('signin.token.submit')}
                </Button>
              </form>
              {!lockedBox && <p className="om-hint">{t('signin.expiry')}</p>}
            </details>
            {alert}
            {lockedBox ? <Button variant="ghost" onClick={onReturnToLock}>{t('lock.return')}</Button> : <p className="dash-signin-links">
              <button type="button" className="om-link" onClick={() => go('setup')}>
                {t('signin.firstTime')}
              </button>
              <button type="button" className="om-link" onClick={() => go('enrol')}>
                {t('signin.haveCode')}
              </button>
            </p>}
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

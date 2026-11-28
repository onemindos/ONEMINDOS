// SPDX-License-Identifier: Apache-2.0
// Password-first sign-in, owner setup at the box, and accepting a family invite (D-034).
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { BrandMark, Button, WallpaperSurface, wallpaperLayers, DEFAULT_APPEARANCE } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import type { WiringApi } from '../api/wiring';
import { ApiError } from '../api/types';
import type { LoginResult } from '../api/wiring';
import { brand } from '../brand.generated';
import { t } from '../i18n';
import { getPasskey, webauthnSupported } from '../lib/webauthn';
import { useSession } from '../session';
import { PasswordRecovery } from './PasswordRecovery';
import { TrustThisBox } from './TrustThisBox';

type View = 'signin' | 'setup' | 'enrol' | 'recovery';

function Field(props: { label: string; name: string; type?: string; value: string; onChange: (v: string) => void; autoComplete?: string; inputMode?: 'numeric'; maxLength?: number; describedBy?: string; invalid?: boolean }) {
  return (
    <>
      <label htmlFor={props.name}>{props.label}</label>
      <input
        id={props.name}
        name={props.name}
        type={props.type ?? 'text'}
        autoComplete={props.autoComplete}
        inputMode={props.inputMode}
        maxLength={props.maxLength}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        aria-invalid={props.invalid ? true : undefined}
        aria-describedby={props.describedBy}
      />
    </>
  );
}

export function SignInCard({ children, locked }: { children: ReactNode; locked?: boolean }) {
  const layers = wallpaperLayers(locked ? 'contour' : DEFAULT_APPEARANCE.wallpaper, null);
  return <main id="main" className="dash-signin">
    {layers && <WallpaperSurface layers={layers} className="dash-signin-wp" />}
    <div className="dash-signin-card">
      <BrandMark className="om-brand-mark dash-signin-mark" />
      {children}
    </div>
  </main>;
}

/** undefined while loading, null for a gateway that does not offer identity setup status. */
function useSetupStatus(api: WiringApi, enabled = true) {
  const [status, setStatus] = useState<components['schemas']['SetupStatus'] | null>();
  useEffect(() => {
    if (!enabled || !api.setupStatus) return;
    let live = true;
    void api.setupStatus().then(
      (data) => { if (live) setStatus(data); },
      () => { if (live) setStatus(null); },
    );
    return () => { live = false; };
  }, [api, enabled]);
  return status;
}

function ownerUsername(name: string): string {
  const candidate = name.normalize('NFKD').toLowerCase().replace(/\p{Mark}/gu, '').replace(/[^a-z0-9]+/g, '-').replace(/^[^a-z]+|-+$/g, '').slice(0, 32);
  return candidate.length >= 2 ? candidate : 'owner';
}

function initialView(): View {
  return hashCode() ? 'enrol' : 'signin';
}
function hashCode(): string {
  return new URLSearchParams(window.location.hash.slice(1)).get('enrol') ?? '';
}

export function SignIn({ mock, lockedBox, onReturnToLock, switchPerson, onEnrolled }: {
  mock: boolean; lockedBox?: string; onReturnToLock?: () => void; switchPerson?: boolean; onEnrolled?: () => void;
}) {
  const { signIn, anon } = useSession();
  const setupStatus = useSetupStatus(anon, !lockedBox);
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
  const [challengeId, setChallengeId] = useState<string>();
  const [boxCode, setBoxCode] = useState('');
  const [codeEntered, setCodeEntered] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [code, setCode] = useState(hashCode);
  const [chipGone, setChipGone] = useState(false);
  const legacySetup = !anon.setupAtBox || (setupStatus != null && !setupStatus.screen);
  const setupAvailable = setupStatus?.state === 'unclaimed' || (!anon.setupStatus && !lockedBox);
  const recoveryAvailable = !!anon.recoveryOptions && setupStatus?.screen && setupStatus.state === 'ready';
  useEffect(() => {
    if (!lockedBox && hashCode()) {
      const clean = new URL(window.location.href);
      const fragment = new URLSearchParams(clean.hash.slice(1));
      fragment.delete('enrol');
      clean.hash = fragment.toString();
      window.history.replaceState(window.history.state, '', clean);
    }
  }, [lockedBox]);
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
    void run('username', async () => finish(await anon.loginPassword({ username: username.trim(), password, ...(totp.trim() ? { totp: totp.trim() } : {}) })), (er) => {
      if (er.reason === 'remote_factor_required' || er.reason === 'totp_required' || er.reason === 'totp_invalid' || er.code === 'rate_limited') return er.message;
      return er.code === 'unauthenticated' ? t('signin.account.bad') : er.message;
    });
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
    if ([...password].length < 12) return fail('password', t('setup.short'));
    if (!legacySetup && !displayName.trim()) return fail('display-name', t('setup.nameRequired'));
    void run(
      legacySetup ? 'setup-token' : 'box-setup-code',
      async () => {
        if (legacySetup) return finish(await anon.setup(setupToken.trim(), { username: username.trim(), display_name: displayName.trim() || username.trim(), password }));
        if (anon.setupAtBox && challengeId) return finish(await anon.setupAtBox({
          challenge_id: challengeId, box_code: boxCode, username: ownerUsername(displayName), display_name: displayName.trim(), password,
        }));
      },
      (er) => {
        if (er.reason === 'already_set_up' || (legacySetup && er.status === 409)) return t('setup.done');
        if (er.code === 'unauthenticated' && legacySetup) return t('setup.badToken');
        if (er.code === 'unauthenticated') { setChallengeId(undefined); setCodeEntered(false); setBoxCode(''); }
        return er.message;
      },
    );
  };
  const requestSetupCode = () => void run('box-setup-code', async () => {
    const options = await anon.setupOptions?.();
    setChallengeId(options?.challenge_id);
    setBoxCode('');
    setCodeEntered(false);
  }, (e) => e.message);
  const onEnrol = (e: FormEvent) => {
    e.preventDefault();
    if ([...password].length < 12) return fail('password', t('setup.short'));
    void run('code', async () => {
      await finish(await anon.enrol({ code: code.trim(), username: username.trim() || undefined, password }));
      if (!mock) onEnrolled?.();
    }, (er) => (er.code === 'unauthenticated' || er.code === 'not_found' ? t('enrol.bad') : er.message));
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
    setTotp('');
    setSetupToken('');
    setChallengeId(undefined);
    setBoxCode('');
    setCodeEntered(false);
  };

  return (
    <SignInCard locked={!!lockedBox}>
        {view === 'signin' && (
          <>
            <h1>{lockedBox ? (switchPerson ? t('lock.switchPerson') : t('lock.unlockTitle', { name: lockedBox })) : t('signin.title', { name: boxName || brand.shortName })}</h1>
            <p className="om-hint">{passkeyOk ? t('signin.lede') : t('signin.passwordOnly')}</p>
            {mock && !lockedBox && !chipGone && (
              <p id={hintId} className="dash-chip">
                <span>{t('signin.mockHint')}</span>
                <button type="button" className="dash-chip-x" aria-label={t('signin.mockHint.dismiss')} onClick={() => setChipGone(true)}>
                  <span aria-hidden="true">×</span>
                </button>
              </p>
            )}
            {!lockedBox && <TrustThisBox />}
            <form onSubmit={onAccount} noValidate className="dash-signin-form">
              <Field label={t('signin.username')} name="username" autoComplete="username" value={username} onChange={setUsername} invalid={bad('username')} describedBy={describe('username')} />
              <Field label={t('signin.password')} name="password" type="password" autoComplete="current-password" value={password} onChange={setPassword} />
              <Field label={t('signin.totp')} name="totp" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={totp} onChange={setTotp} />
              <Button type="submit" variant="primary" disabled={busy}>{t('signin.account.submit')}</Button>
            </form>
            {/* D-034: passkeys are optional; the password form comes first and the passkey is the other choice. */}
            {passkeyOk && <p className="dash-signin-or" aria-hidden="true"><span>{t('signin.or')}</span></p>}
            {passkeyOk && <Button onClick={onPasskey} disabled={busy}>{t('signin.passkey')}</Button>}
            <details className="dash-signin-more" open={!passkeyOk || undefined}>
              <summary>{t('signin.more')}</summary>
              <form onSubmit={onToken} noValidate className="dash-signin-form">
                <h2 className="dash-signin-sub">{t('signin.token.heading')}</h2>
                <Field label={t('signin.token.label')} name="token" type="password" autoComplete="off" value={token} onChange={setToken} invalid={bad('token')} describedBy={describe('token', mock && !lockedBox && !chipGone ? hintId : undefined)} />
                <Button type="submit" disabled={busy}>
                  {busy ? t('signin.busy') : t('signin.token.submit')}
                </Button>
              </form>
              {!lockedBox && <p className="om-hint">{t('signin.expiry')}</p>}
            </details>
            {alert}
            {lockedBox ? <Button variant="ghost" onClick={onReturnToLock}>{t('lock.return')}</Button> : <p className="dash-signin-links">
              {setupAvailable && <button type="button" className="om-link" onClick={() => go('setup')}>
                {t('signin.firstTime')}
              </button>}
              <button type="button" className="om-link" onClick={() => go('enrol')}>
                {t('signin.haveCode')}
              </button>
              {recoveryAvailable && <button type="button" className="om-link" onClick={() => go('recovery')}>{t('recovery.forgot')}</button>}
            </p>}
          </>
        )}
        {view === 'setup' && (
          <>
            <h1>{t('setup.title')}</h1>
            {legacySetup || codeEntered ? <form onSubmit={onSetup} noValidate className="dash-signin-form">
              {legacySetup && <>
                <p className="om-hint">{t('setup.lede')}</p>
                <Field label={t('setup.token')} name="setup-token" type="password" autoComplete="off" value={setupToken} onChange={setSetupToken} invalid={bad('setup-token')} describedBy={describe('setup-token')} />
                <Field label={t('setup.username')} name="username" autoComplete="username" value={username} onChange={setUsername} />
              </>}
              <Field label={t('setup.displayName')} name="display-name" autoComplete="name" value={displayName} onChange={setDisplayName} invalid={bad('display-name')} describedBy={describe('display-name')} />
              {!legacySetup && displayName.trim() && <p className="om-hint">{t('setup.signinAs', { username: ownerUsername(displayName) })}</p>}
              <Field label={t('setup.password')} name="password" type="password" autoComplete="new-password" value={password} onChange={setPassword} invalid={bad('password')} describedBy={describe('password')} />
              <Button type="submit" variant="primary" disabled={busy}>{t('setup.submit')}</Button>
            </form> : challengeId ? <form onSubmit={(e) => { e.preventDefault(); if (/^\d{6}$/.test(boxCode)) { setCodeEntered(true); setError(undefined); } }} className="dash-signin-form">
              <p className="om-hint">{t('setup.codeShown')}</p>
              <Field label={t('setup.boxCode')} name="box-setup-code" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={boxCode} onChange={setBoxCode} invalid={bad('box-setup-code')} describedBy={describe('box-setup-code')} />
              <Button type="submit" variant="primary" disabled={busy || !/^\d{6}$/.test(boxCode)}>{t('setup.continue')}</Button>
              <Button type="button" variant="ghost" disabled={busy} onClick={requestSetupCode}>{t('setup.newCode')}</Button>
            </form> : <>
              <p className="om-hint">{t('setup.screen')}</p>
              <Button type="button" variant="primary" onClick={requestSetupCode} disabled={busy}>{t('setup.showCode')}</Button>
            </>}
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
        {view === 'recovery' && <PasswordRecovery api={anon} onBack={() => go('signin')} />}
    </SignInCard>
  );
}

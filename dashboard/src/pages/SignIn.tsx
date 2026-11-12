// SPDX-License-Identifier: Apache-2.0
// Sign-in with the static bearer token of contract §3 (passkeys come with CORE-SEC-2).
import { useId, useState, type FormEvent } from 'react';
import { BrandMark, Button } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useSession } from '../session';
import { brand } from '../brand.generated';

export function SignIn({ mock }: { mock: boolean }) {
  const { signIn } = useSession();
  const [token, setToken] = useState('');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const errId = useId();
  const hintId = useId();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) {
      setError('Enter your access token.');
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await signIn(token);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'unauthenticated') setError('That token was not accepted by the hub.');
      else setError(`Could not reach the hub${err instanceof Error ? ` (${err.message})` : ''}.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main id="main" className="dash-signin">
      <div className="dash-signin-card">
        <BrandMark className="om-brand-mark dash-signin-mark" />
        <h1>Welcome to {brand.shortName}</h1>
        <p className="om-hint">Sign in with the access token your hub gave you.</p>
        <form onSubmit={onSubmit} noValidate className="dash-signin-form">
          <label htmlFor="token">Access token</label>
          <input
            id="token"
            name="token"
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={[mock ? hintId : '', error ? errId : ''].filter(Boolean).join(' ') || undefined}
          />
          {mock && (
            <p id={hintId} className="om-hint">
              Demo mode: try <code>owner-demo</code>, <code>agent-demo</code> or <code>adult-demo</code>.
            </p>
          )}
          {error && (
            <p id={errId} className="om-note om-tone-bad" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
        <p className="om-hint">
          This hub version uses a static token. Passkeys and accounts come with CORE-SEC-2.
        </p>
      </div>
    </main>
  );
}

import { useId, useState, type FormEvent } from 'react';
import { ApiError } from '../api/types';
import { useSession } from '../session';

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
    <main id="main" className="signin">
      <div className="signin-card">
        <span className="brand-mark brand-mark-lg" aria-hidden="true" />
        <h1>Welcome to OneMind</h1>
        <p className="muted">Sign in with the access token your hub gave you.</p>
        <form onSubmit={onSubmit} noValidate>
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
            <p id={hintId} className="hint">
              Demo mode: try <code>owner-demo</code>, <code>agent-demo</code> or <code>adult-demo</code>.
            </p>
          )}
          {error && (
            <p id={errId} className="note note-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="fineprint">
          v0 uses a static token. Passkeys and accounts come later.
        </p>
      </div>
    </main>
  );
}

import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { ApiError, type CatalogApp } from '../api/types';
import { AppIcon, ErrorNote, Loading } from '../components/bits';
import { useNow, usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';

/** How long an owner has to approve a request made from the Market. */
export const REQUEST_TTL_MS = 60 * 60 * 1000;

/**
 * `status` values (§3 catalog) other than installed / not_installed. While a change
 * is running the button is disabled; after a failed or unknown outcome the hub
 * accepts a new install or remove, so the button stays live and the state is shown.
 */
const IN_FLIGHT: Record<string, string> = { installing: 'Installing…', removing: 'Removing…' };
const PROBLEM: Record<string, string> = { failed: 'Last change failed', unknown: 'State unknown' };

export function Market() {
  const { api, canRequest } = useSignedIn();
  const now = useNow();
  const navigate = useNavigate();
  const apps = usePoll(() => api.apps(), 30_000);
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  // One idempotency key per (type, app) until the hub gives a definite answer, so
  // retrying after a lost response returns the same action instead of a second one (§3).
  const pendingKeys = useRef(new Map<string, { key: string; expiresAt: string }>());

  async function request(app: CatalogApp) {
    setBusy(app.id);
    setError(undefined);
    const type = app.installed ? 'app.remove' : 'app.install';
    const slot = `${type}:${app.id}`;
    let pending = pendingKeys.current.get(slot);
    if (!pending) {
      pending = { key: uuidv4(), expiresAt: new Date(Date.now() + REQUEST_TTL_MS).toISOString() };
      pendingKeys.current.set(slot, pending);
    }
    try {
      const action = await api.createAction({
        type,
        params: { app_id: app.id },
        idempotency_key: pending.key,
        expires_at: pending.expiresAt,
      });
      pendingKeys.current.delete(slot);
      navigate(`/approvals?highlight=${encodeURIComponent(action.id)}`);
      return; // this screen unmounts; no more state updates here
    } catch (e) {
      // Keep the key only when the outcome is unknown (network error or 5xx).
      const definite = e instanceof ApiError && e.status >= 400 && e.status < 500;
      if (definite || !(e instanceof ApiError)) pendingKeys.current.delete(slot);
      setError(
        e instanceof ApiError && e.code === 'permission_denied'
          ? 'Your account cannot request installs. Ask the owner.'
          : `Request failed${e instanceof Error ? `: ${e.message}` : ''}.`,
      );
    }
    setBusy(undefined);
  }

  return (
    <div className="page">
      <h1>Market</h1>
      <p className="lede">
        Installing or removing an app creates a request. Nothing changes until the owner approves it on the Approvals
        screen.
      </p>
      {canRequest === 'no' && (
        <p className="note">Your account can browse the Market, but only the owner (or an agent) can make requests.</p>
      )}
      {error && (
        <p className="note note-error" role="alert">
          {error}
        </p>
      )}
      {apps.error && <ErrorNote error={apps.error} fetchedAt={apps.fetchedAt} now={now} />}
      {apps.loading && !apps.data ? (
        <Loading what="the catalog" />
      ) : (
        <ul className="card-grid">
          {(apps.data ?? []).map((a) => {
            const titleId = `app-${a.id}`;
            const inFlight = IN_FLIGHT[a.status];
            const problem = PROBLEM[a.status];
            return (
              <li key={a.id}>
                <article className="app-card" aria-labelledby={titleId}>
                  <div className="app-card-head">
                    <AppIcon id={a.id} name={a.name} size={64} />
                    <div>
                      <h2 id={titleId}>{a.name}</h2>
                      <p className="small">
                        {a.category} · v{a.version}
                        {a.installed && <span className="badge badge-installed">Installed</span>}
                        {inFlight && <span className="badge badge-app-state badge-stale">{inFlight}</span>}
                        {problem && <span className="badge badge-app-state badge-state-failed">{problem}</span>}
                      </p>
                    </div>
                  </div>
                  <p>{a.description}</p>
                  <dl className="facts facts-compact">
                    <div>
                      <dt>Runs on</dt>
                      <dd>{a.archs.join(', ')}</dd>
                    </div>
                    <div>
                      <dt>Needs</dt>
                      <dd>
                        {a.requires.gpu ? 'GPU, ' : ''}
                        {a.requires.minMemoryMb ? `${a.requires.minMemoryMb} MB memory` : 'no special hardware'}
                      </dd>
                    </div>
                    <div>
                      <dt>Licence</dt>
                      <dd>{a.license}</dd>
                    </div>
                  </dl>
                  <div className="app-card-actions">
                    <button
                      type="button"
                      className={a.installed ? 'btn btn-ghost' : 'btn btn-primary'}
                      disabled={busy !== undefined || canRequest === 'no' || inFlight !== undefined}
                      onClick={() => void request(a)}
                    >
                      {busy === a.id
                        ? 'Requesting…'
                        : inFlight
                          ? `${inFlight.slice(0, -1)} ${a.name}…`
                          : a.installed
                            ? `Remove ${a.name}`
                            : `Install ${a.name}`}
                    </button>
                    <a href={a.source} target="_blank" rel="noreferrer" className="small">
                      Source<span className="visually-hidden"> code for {a.name} (opens in a new tab)</span>
                    </a>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

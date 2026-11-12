import { Link } from 'react-router';
import { AppIcon, ErrorNote, Loading } from '../components/bits';
import { AppLinksList, IN_FLIGHT, RequestButton, TrustFacts } from '../components/AppTrust';
import { useNow, usePoll } from '../lib/hooks';
import { hubNow } from '../lib/time';
import { useAppRequest } from '../lib/useAppRequest';
import { useSignedIn } from '../session';

/**
 * `status` values (§3 catalog) other than installed / not_installed. While a change
 * is running the button is disabled; after a failed or unknown outcome the hub
 * accepts a new install or remove, so the button stays live and the state is shown.
 */
const PROBLEM: Record<string, string> = { failed: 'Last change failed', unknown: 'State unknown' };

export function Market() {
  const { api, canRequest } = useSignedIn();
  const now = useNow();
  const apps = usePoll(() => api.apps(), 30_000);
  const { busy, error, request } = useAppRequest();
  const hubTime = hubNow(now, { hubOffsetMs: api.hubOffsetMs() });

  return (
    <div className="page">
      <h1>Market</h1>
      <p className="lede">
        Installing or removing an app creates a request. Nothing changes until the owner approves it on the Approvals
        screen. Only apps that passed a security scan in the last 7 days can be installed.
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
                      <h2 id={titleId}>
                        <Link to={`/market/${encodeURIComponent(a.id)}`}>{a.name}</Link>
                      </h2>
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
                    <TrustFacts app={a} />
                  </dl>
                  <AppLinksList app={a} />
                  <div className="app-card-actions">
                    <RequestButton
                      app={a}
                      hubNow={hubTime}
                      busy={busy}
                      canRequest={canRequest}
                      onRequest={(app) => void request(app)}
                    />
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

// SPDX-License-Identifier: Apache-2.0
import { Link, useParams } from 'react-router';
import { AppIcon, ErrorNote, Loading } from '../components/bits';
import { AppLinksList, IN_FLIGHT, RequestButton, TrustFacts } from '../components/AppTrust';
import { useNow, usePoll } from '../lib/hooks';
import { hubNow } from '../lib/time';
import { useAppRequest } from '../lib/useAppRequest';
import { useSignedIn } from '../session';

/**
 * One app's page (§9.3, §11.4): what it is, its links, licence, tier and last scan next to
 * Install. Built from GET /v1/apps; the contract has no single-app route.
 */
export function AppDetail() {
  const { appId = '' } = useParams();
  const { api, canRequest } = useSignedIn();
  const now = useNow();
  const apps = usePoll(() => api.apps(), 30_000);
  const { busy, error, request } = useAppRequest();
  const app = apps.data?.find((a) => a.id === appId);
  const back = (
    <p>
      <Link to="/market">Back to the Market</Link>
    </p>
  );

  if (apps.loading && !apps.data) return <div className="page">{back}<Loading what="the app" /></div>;
  if (!app)
    return (
      <div className="page">
        {back}
        <h1>App not found</h1>
        {apps.error ? (
          <ErrorNote error={apps.error} fetchedAt={apps.fetchedAt} now={now} />
        ) : (
          <p className="note">The Market has no app called “{appId}”.</p>
        )}
      </div>
    );

  const inFlight = IN_FLIGHT[app.status];
  return (
    <div className="page">
      {back}
      <section className="glass app-detail" aria-labelledby="app-title">
        <div className="app-card-head">
          <AppIcon id={app.id} name={app.name} size={72} />
          <div>
            <h1 id="app-title" className="app-detail-title">
              {app.name}
            </h1>
            <p className="small">
              {app.category} · v{app.version}
              {app.installed && <span className="badge badge-installed">Installed</span>}
              {inFlight && <span className="badge badge-app-state badge-stale">{inFlight}</span>}
            </p>
          </div>
        </div>
        <p>{app.description}</p>
        {error && (
          <p className="note note-error" role="alert">
            {error}
          </p>
        )}
        {apps.error && <ErrorNote error={apps.error} fetchedAt={apps.fetchedAt} now={now} />}
        <div className="app-detail-install">
          <RequestButton
            app={app}
            hubNow={hubNow(now, { hubOffsetMs: api.hubOffsetMs() })}
            busy={busy}
            canRequest={canRequest}
            onRequest={(a) => void request(a)}
          />
        </div>
        <h2>Trust</h2>
        <dl className="facts facts-compact">
          <TrustFacts app={app} />
        </dl>
        <h2>Links</h2>
        <AppLinksList app={app} />
        <h2>Requirements</h2>
        <dl className="facts facts-compact">
          <div>
            <dt>Runs on</dt>
            <dd>{app.archs.join(', ')}</dd>
          </div>
          <div>
            <dt>Memory</dt>
            <dd>{app.requires.minMemoryMb ? `${app.requires.minMemoryMb} MB` : 'no minimum'}</dd>
          </div>
          <div>
            <dt>GPU</dt>
            <dd>{app.requires.gpu ? 'required' : 'not needed'}</dd>
          </div>
          <div>
            <dt>Web port</dt>
            <dd>{app.web_port ?? 'none'}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

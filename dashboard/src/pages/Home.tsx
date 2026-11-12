import { Link } from 'react-router';
import type { NodeStatus } from '../api/types';
import { AppIcon, ErrorNote, Loading, StatusBadge } from '../components/bits';
import { useNow, usePoll } from '../lib/hooks';
import { effectiveStatus, formatAgo } from '../lib/time';
import { useSignedIn } from '../session';

function greeting(now: number) {
  const h = new Date(now).getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

export function Home() {
  const { api } = useSignedIn();
  const now = useNow();
  const instance = usePoll(() => api.instance(), 60_000);
  const nodes = usePoll(() => api.nodes());
  const apps = usePoll(() => api.apps(), 30_000);
  const actions = usePoll(() => api.actions());

  const counts: Record<NodeStatus, number> = { online: 0, stale: 0, offline: 0 };
  for (const n of nodes.data ?? []) counts[effectiveStatus(n.status, n.last_seen, now)]++;
  const installed = (apps.data ?? []).filter((a) => a.installed);
  const pending = (actions.data ?? []).filter((a) => a.state === 'awaiting_approval').length;
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';

  return (
    <div className="page home">
      <section className="hero" aria-labelledby="home-title">
        <p className="hero-greeting">{greeting(now)}</p>
        <h1 id="home-title">{instance.data?.name ?? 'OneMind'}</h1>
        {instance.data && (
          <p className="muted-on-wall">
            Version {instance.data.version} · hub node <code>{instance.data.hub_node_id}</code>
          </p>
        )}
        {instance.error && <ErrorNote error={instance.error} fetchedAt={instance.fetchedAt} now={now} />}
      </section>

      <section aria-labelledby="sum-title" className="glass">
        <h2 id="sum-title">Machines</h2>
        {nodes.loading && !nodes.data ? (
          <Loading what="machines" />
        ) : (
          <ul className="stat-row">
            {(['online', 'stale', 'offline'] as const).map((s) => (
              <li key={s} className="stat">
                <span className="stat-num">{counts[s]}</span>
                <StatusBadge status={s} />
              </li>
            ))}
          </ul>
        )}
        {nodes.error && <ErrorNote error={nodes.error} fetchedAt={nodes.fetchedAt} now={now} />}
        <p className="small">
          {nodes.fetchedAt !== undefined && <>Checked {formatAgo(Math.floor((now - nodes.fetchedAt) / 1000))}. </>}
          <Link to="/nodes">See all machines</Link>
          {pending > 0 && (
            <>
              {' · '}
              <Link to="/approvals">
                {pending} request{pending === 1 ? '' : 's'} waiting for approval
              </Link>
            </>
          )}
        </p>
      </section>

      <section aria-labelledby="apps-title" className="glass">
        <h2 id="apps-title">Your apps</h2>
        {apps.loading && !apps.data ? (
          <Loading what="apps" />
        ) : installed.length === 0 ? (
          <p>
            No apps yet. <Link to="/market">Browse the Market</Link>.
          </p>
        ) : (
          <ul className="app-grid">
            {installed.map((a) => (
              <li key={a.id}>
                {a.web_port ? (
                  <a className="app-tile" href={`http://${host}:${a.web_port}/`} target="_blank" rel="noreferrer">
                    <AppIcon id={a.id} name={a.name} />
                    <span className="app-tile-name">{a.name}</span>
                    <span className="visually-hidden"> (opens in a new tab)</span>
                  </a>
                ) : (
                  <span className="app-tile">
                    <AppIcon id={a.id} name={a.name} />
                    <span className="app-tile-name">{a.name}</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {apps.error && <ErrorNote error={apps.error} fetchedAt={apps.fetchedAt} now={now} />}
      </section>
    </div>
  );
}

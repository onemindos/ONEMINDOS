import { NavLink, Outlet } from 'react-router';
import { useSignedIn } from '../session';
import { usePoll } from '../lib/hooks';
import { brand } from '../brand.generated';

export function Layout() {
  const { api, principal, signOut, mock } = useSignedIn();
  const actions = usePoll(() => api.actions(), 10_000);
  const pending = actions.data?.filter((a) => a.state === 'awaiting_approval').length ?? 0;

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <span className="brand">
          <img className="brand-mark" src={brand.logo.onDark} alt="" />
          {brand.shortName}
        </span>
        <nav aria-label="Main">
          <ul className="nav">
            <li>
              <NavLink to="/" end>
                Home
              </NavLink>
            </li>
            <li>
              <NavLink to="/nodes">Nodes</NavLink>
            </li>
            <li>
              <NavLink to="/market">Market</NavLink>
            </li>
            <li>
              <NavLink to="/approvals">
                Approvals
                {pending > 0 && (
                  <span className="count">
                    {pending}
                    <span className="visually-hidden"> pending</span>
                  </span>
                )}
              </NavLink>
            </li>
          </ul>
        </nav>
        <div className="who">
          {mock && <span className="badge badge-mock">Demo data</span>}
          {principal && (
            <span className="who-name">
              {principal.id} ({principal.role})
            </span>
          )}
          <button type="button" className="btn btn-ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}

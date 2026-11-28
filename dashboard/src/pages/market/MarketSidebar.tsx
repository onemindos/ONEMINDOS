// SPDX-License-Identifier: Apache-2.0
// Atlas Market (prototype 04): the sidebar of the Market window. Counts come from the hub's own
// answers (catalog, actions, GET /v1/sources); a count the hub has not sent is left out, never guessed.
// "Bring your own" puts custom apps next to the catalog (founder 2026-11-25, D-026): each entry opens
// the page that files the request, and every one of them still waits in Approvals (D-027).
import type { ReactNode } from 'react';
import { Icon, type IconName } from '@onemind/ui';
import { useHub } from '../../data/hub';
import { usePoll } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';
import { isAppRequest } from './requests';
import './market.css';

export type MarketPlace = 'discover' | 'installed' | 'builtin' | 'requests' | 'plugins' | 'app';

function Item({ to, icon, label, count, current }: { to: string; icon: IconName; label: string; count?: number; current?: boolean }) {
  return (
    <li>
      <a href={to} className="dash-mkt-nav-item" aria-current={current ? 'page' : undefined}>
        <Icon name={icon} size={18} />
        <span className="dash-mkt-nav-label">{label}</span>
        {count !== undefined && <span className="dash-mkt-nav-n" aria-label={`${count}`}>{count}</span>}
      </a>
    </li>
  );
}

export function MarketSidebar({ current }: { current: MarketPlace }) {
  const hub = useHub();
  const { api, canDecide } = useSignedIn();
  const owner = canDecide !== 'no';
  const apps = hub.apps.data;
  const installed = apps?.filter((a) => a.installed).length;
  const verified = apps?.filter((a) => a.tier === 'verified').length;
  const waiting = hub.actions.data !== undefined ? hub.actionList.filter((a) => isAppRequest(a) && a.state === 'awaiting_approval').length : undefined;
  // Community sources are owner-only on the hub (§12.22): other roles never ask for them.
  const sources = usePoll(async () => {
    if (!owner || !api.sources) return [];
    return api.sources();
  }, 60_000);

  return (
    <nav aria-label="Market" className="dash-mkt-nav">
      <ul className="dash-mkt-nav-list">
        <Item to={href.market} icon="search" label="Discover" current={current === 'discover'} />
        <Item to={href.installed} icon="check" label="Installed" count={installed} current={current === 'installed'} />
        <Item to={href.updates} icon="updates" label="Updates" />
        <Item to={href.marketRequests} icon="clock" label="Requests" count={waiting} current={current === 'requests'} />
        <Item to={href.builtIn} icon="hub" label="Built in" current={current === 'builtin'} />
      </ul>
      {owner && (
        <>
          <h2 className="dash-mkt-nav-head">Bring your own</h2>
          <ul className="dash-mkt-nav-list">
            <Item to={href.compose} icon="apps" label="Any container image" />
            <Item to={href.compose} icon="storage" label="Compose file" />
            <Item to={href.custom} icon="link" label="Git repository" />
            <Item to={`${href.market}?plugins=1`} icon="plus" label="Plugin" current={current === 'plugins'} />
          </ul>
        </>
      )}
      <h2 className="dash-mkt-nav-head">Sources</h2>
      <ul className="dash-mkt-nav-list">
        <li className="dash-mkt-nav-item dash-mkt-nav-static">
          <span className="dash-mkt-dot" aria-hidden="true" />
          <span className="dash-mkt-nav-label">OneMind verified</span>
          {verified !== undefined && <span className="dash-mkt-nav-n">{verified}</span>}
        </li>
        {(sources.data ?? []).map((s) => (
          <li key={s.id} className="dash-mkt-nav-item dash-mkt-nav-static">
            <span className={s.errors.length ? 'dash-mkt-dot dash-mkt-dot-warn' : 'dash-mkt-dot'} aria-hidden="true" />
            <span className="dash-mkt-nav-label">{s.name}{s.errors.length ? <span className="om-visually-hidden"> (has errors)</span> : null}</span>
            <span className="dash-mkt-nav-n">{s.apps.length}</span>
          </li>
        ))}
        {owner && <Item to={href.sources} icon="plus" label="Add a source" />}
      </ul>
    </nav>
  );
}

/** The Market window body: the sidebar, then the page. Below the narrow breakpoint the sidebar stacks on top. */
export function MarketLayout({ current, children }: { current: MarketPlace; children: ReactNode }) {
  return (
    <div className="dash-mkt">
      <MarketSidebar current={current} />
      <div className="dash-mkt-main">{children}</div>
    </div>
  );
}

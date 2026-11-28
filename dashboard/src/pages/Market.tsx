// SPDX-License-Identifier: Apache-2.0
// Market: Discover (editorial rails + category rails from TAXONOMY §1), search and filters, and the
// app page with its trust card (scan, tier, licence, links; §11.4). Install is a request (§3):
// POST /v1/actions → Approvals, then the app page follows the action live until it ends.
import { AppMachineFit } from './AppMachineFit';
import { useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { AppDetail, Market as StoreMarket, PageHeader, type Collection, type LoadState } from '@onemind/ui';
import { openUrl, toStoreApp } from '../data/adapters';
import { openAppOrSay } from '../lib/openApp';
import { useSignedIn } from '../session';
import { ActionStatus } from '../shell/ActionJobs';
import { AppDepth } from './AppDepth';
import { useHub, type Hub } from '../data/hub';
import type { Polled } from '../lib/hooks';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { AppWaitingTrack } from './market/AppWaitingTrack';
import { BringYourOwn } from './market/BringYourOwn';
import { MarketLayout } from './market/MarketSidebar';

/**
 * Editorial rails (PU-11: a repo file, not an API). Ids missing from the catalog are skipped,
 * so a rail never shows an app the hub cannot install.
 */
export const COLLECTIONS: Collection[] = [
  { id: 'start', title: 'Start here', blurb: 'Small, useful first apps that run on any node.', app_ids: ['vaultwarden', 'uptime-kuma', 'ntfy', 'actual-budget'] },
  { id: 'smart-home', title: 'For the smart home', blurb: 'Local control, no vendor cloud.', app_ids: ['home-assistant', 'mosquitto', 'zigbee2mqtt', 'node-red'] },
  { id: 'browsers', title: 'Browsers', blurb: 'A full browser on your box, shown in a window. The profile stays on the box, and you sign in with the login the box made for you.', app_ids: ['firefox', 'chromium'] },
];
export const FEATURED = { app_id: 'vaultwarden', headline: 'Your passwords, on your own box', blurb: 'Vaultwarden works with the Bitwarden apps you already know, and nothing leaves home.' };

/** A poll's answer as the store's load state: stale data is kept and labelled, never shown as live. */
export function loadState<T>(p: Polled<T>, hub: Pick<Hub, 'freshness' | 'asOf'>): LoadState {
  if (p.data === undefined) return p.error ? { kind: 'error', code: p.error.code, message: p.error.message } : { kind: 'loading' };
  const fetched = hub.asOf ?? new Date().toISOString();
  return { kind: 'ready', fetched_at: fetched, stale: hub.freshness === 'stale' || hub.freshness === 'offline' || !!p.error };
}

/** Explains the v0 placement rule wherever a node would be chosen. */
export const PLACEMENT_NOTE = 'The hub picks the node (Kubernetes places it). A per-node preview comes with §12 plans.';

function StoreTabs({ current }: { current: 'discover' | 'installed' | 'builtin' | 'sources' | 'compose' | 'custom' }) {
  // Community sources and Compose import are owner-only: other roles do not see the tabs.
  const { canDecide } = useSignedIn();
  const owner = canDecide !== 'no';
  return (
    <nav aria-label="Market" className="dash-tabs">
      <a href={href.market} aria-current={current === 'discover' ? 'page' : undefined}>
        Discover
      </a>
      <a href={href.installed} aria-current={current === 'installed' ? 'page' : undefined}>
        Installed
      </a>
      <a href={href.builtIn} aria-current={current === 'builtin' ? 'page' : undefined}>
        Built in
      </a>
      {owner && (
        <a href={href.sources} aria-current={current === 'sources' ? 'page' : undefined}>
          Sources
        </a>
      )}
      {owner && (
        <a href={href.custom} aria-current={current === 'custom' ? 'page' : undefined}>
          Custom apps
        </a>
      )}
      {owner && (
        <a href={href.compose} aria-current={current === 'compose' ? 'page' : undefined}>
          Import Compose
        </a>
      )}
    </nav>
  );
}
export { StoreTabs };

export function Market() {
  const hub = useHub();
  const shell = useShell();
  const { api } = useSignedIn();
  const navigate = useNavigate();
  const { appId } = useParams();
  const [search] = useSearchParams();
  const pluginsOnly = search.get('plugins') === '1';
  const apps = useMemo(() => (hub.apps.data ?? []).map(toStoreApp), [hub.apps.data]);
  const state = loadState(hub.apps, hub);
  const byId = (id: string) => hub.apps.data?.find((a) => a.id === id);
  const open = (id: string) => {
    const a = byId(id);
    if (a?.browser && a.installed) return navigate(href.browser(id));  // #692: a window with the person's own profile
    const url = a ? openUrl(a) : undefined;
    if (a && url) openAppOrSay(api, a.name || a.id, url);
    else navigate(href.manage(id));
  };
  const appJob = hub.actionList.find((a) => a.params.app_id === appId);
  // Atlas 05: an install or update for this app that waits for an owner gets the waiting track.
  const waiting = hub.actionList.find((a) => a.params.app_id === appId && a.state === 'awaiting_approval' && (a.type === 'app.install' || a.type === 'app.update'));
  // Bring your own files owner-only requests (custom apps, Compose import), so only owners see it.
  const canRequestOwn = hub.canDecide !== 'no' && !pluginsOnly;
  const isChild = shell.role === 'child';
  const blockedForYou =
    hub.canRequest === 'no' ? (isChild ? 'You cannot install apps yourself. Ask a parent.' : 'Your account can look but not request installs. Ask the owner.') : undefined;
  // No hub route lets a child file a request yet, so "Ask a parent" is a plain instruction, never a
  // button that would pretend to send something.
  const askParent = isChild && blockedForYou ? <p className="om-note om-tone-info" role="note"><strong>Ask a parent.</strong> Tell them which app you would like. A parent can install it from the Market.</p> : null;

  // A request goes straight to the hub and lands in Approvals, where the owner sees the exact
  // request (type, app, who asked) before anything runs. Nothing is installed until it is approved.
  const request = (type: 'app.install' | 'app.remove', id: string) => {
    if (blockedForYou) return;
    void shell.requestApp(type, id).then((actionId) => actionId && navigate(href.approval(actionId)));
  };

  if (appId) {
    const app = apps.find((a) => a.id === appId);
    return (
      <MarketLayout current="app">
        {waiting && <AppWaitingTrack key={waiting.id} action={waiting} app={hub.apps.data?.find((a) => a.id === appId)} />}
        <AppDetail
          app={app}
          state={state}
          planState={{ kind: 'ready', fetched_at: hub.asOf ?? new Date().toISOString() }}

          now={hub.now}
          backHref={href.market}
          manageHref={href.manage}
          onRequestInstall={(a) => request('app.install', a.id)}
          onOpen={(a) => open(a.id)}
          onRetry={hub.reloadAll}
          requestBlocked={blockedForYou ?? (waiting ? `An ${waiting.type === 'app.update' ? 'update' : 'install'} request for this app is already waiting for approval.` : undefined)}
        />
        {appJob && appJob !== waiting && <ActionStatus action={appJob} label="App request progress" now={hub.now} />}
        {app && shell.view === "pro" && <AppMachineFit key={appId} appId={appId} />}
        {app && <AppDepth key={appId} appId={appId} />}
        {blockedForYou && <p className="om-note om-tone-info">{blockedForYou}</p>}
        {askParent}
      </MarketLayout>
    );
  }

  return (
    <MarketLayout current={pluginsOnly ? 'plugins' : 'discover'}>
      <PageHeader title="Market" lede="Every app is checked for licence, vulnerabilities and malware before it is offered. Installing is a request: the owner approves it first." />
      {blockedForYou && <p className="om-note om-tone-info">{blockedForYou}</p>}
      {askParent}
      <StoreMarket
        key={pluginsOnly ? 'plugins' : 'all'}
        initialFilters={pluginsOnly ? { pluginsOnly: true } : undefined}
        apps={apps}
        state={state}
        now={hub.now}
        collections={COLLECTIONS}
        featured={apps.some((a) => a.id === FEATURED.app_id) ? FEATURED : undefined}

        appHref={href.app}
        approvalsHref={href.approvals}
        onOpen={(a) => open(a.id)}
        onRequestRemove={(a) => request('app.remove', a.id)}
        onRequestInstall={(a) => request('app.install', a.id)}
        onRetry={hub.reloadAll}
        requestBlocked={blockedForYou}
      />
      {canRequestOwn && <BringYourOwn />}
    </MarketLayout>
  );
}

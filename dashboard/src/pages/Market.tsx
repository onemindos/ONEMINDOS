// SPDX-License-Identifier: Apache-2.0
// Market: Discover (editorial rails + category rails from TAXONOMY §1), search and filters, and the
// app page with its trust card (scan, tier, licence, links; §11.4). Install is a request (§3):
// review → POST /v1/actions → the app page follows the action live until it ends.
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { AppDetail, InstallReview, Market as StoreMarket, PageHeader, type CatalogApp as StoreApp, type Collection, type LoadState } from '@onemind/ui';
import { toJob, toStoreApp } from '../data/adapters';
import { useHub, type Hub } from '../data/hub';
import type { Polled } from '../lib/hooks';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';

/**
 * Editorial rails (PU-11: a repo file, not an API). Ids missing from the catalog are skipped,
 * so a rail never shows an app the hub cannot install.
 */
export const COLLECTIONS: Collection[] = [
  { id: 'start', title: 'Start here', blurb: 'Small, useful first apps that run on any node.', app_ids: ['vaultwarden', 'uptime-kuma', 'ntfy', 'actual-budget'] },
  { id: 'smart-home', title: 'For the smart home', blurb: 'Local control, no vendor cloud.', app_ids: ['home-assistant', 'mosquitto', 'zigbee2mqtt', 'node-red'] },
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

function StoreTabs({ current }: { current: 'discover' | 'installed' }) {
  return (
    <nav aria-label="Market" className="dash-tabs">
      <a href={href.market} aria-current={current === 'discover' ? 'page' : undefined}>
        Discover
      </a>
      <a href={href.installed} aria-current={current === 'installed' ? 'page' : undefined}>
        Installed
      </a>
    </nav>
  );
}
export { StoreTabs };

export function Market() {
  const hub = useHub();
  const shell = useShell();
  const navigate = useNavigate();
  const { appId } = useParams();
  const [review, setReview] = useState<StoreApp | null>(null);
  const apps = useMemo(() => (hub.apps.data ?? []).map(toStoreApp), [hub.apps.data]);
  const state = loadState(hub.apps, hub);
  const byId = (id: string) => hub.apps.data?.find((a) => a.id === id);
  const open = (id: string) => {
    const a = byId(id);
    if (a?.installed && a.web_port) window.open(`${window.location.protocol}//${window.location.hostname}:${a.web_port}/`, '_blank', 'noopener');
    else navigate(href.manage(id));
  };
  const jobs = hub.actionList.filter((a) => a.type === 'app.install').map((a) => toJob(a, hub.appName(a.params.app_id)));
  const blockedForYou = hub.canRequest === 'no' ? 'Your account can look but not request installs. Ask the owner.' : undefined;

  const reviewDialog = review && (
    <InstallReview
      key={review.id}
      app={review}
      open
      now={hub.now}
      placementNote={PLACEMENT_NOTE}
      onClose={() => setReview(null)}
      onSubmit={(r) => {
        void shell.requestApp('app.install', r.params.app_id).then((id) => id && navigate(href.app(r.params.app_id)));
      }}
    />
  );

  if (appId) {
    const app = apps.find((a) => a.id === appId);
    return (
      <>
        <AppDetail
          app={app}
          state={state}
          planState={{ kind: 'ready', fetched_at: hub.asOf ?? new Date().toISOString() }}
          job={jobs.find((j) => j.app_id === appId)}
          now={hub.now}
          backHref={href.market}
          manageHref={href.manage}
          onRequestInstall={(a) => (blockedForYou ? undefined : setReview(a))}
          onOpen={(a) => open(a.id)}
          onRetry={hub.reloadAll}
        />
        {blockedForYou && <p className="om-note om-tone-info">{blockedForYou}</p>}
        {reviewDialog}
      </>
    );
  }

  return (
    <>
      <PageHeader title="Market" lede="Every app is checked for licence, vulnerabilities and malware before it is offered. Installing is a request: the owner approves it first." />
      <StoreTabs current="discover" />
      {blockedForYou && <p className="om-note om-tone-info">{blockedForYou}</p>}
      <StoreMarket
        apps={apps}
        state={state}
        now={hub.now}
        collections={COLLECTIONS}
        featured={apps.some((a) => a.id === FEATURED.app_id) ? FEATURED : undefined}
        jobs={jobs}
        appHref={href.app}
        approvalsHref={href.approvals}
        onOpen={(a) => open(a.id)}
        onRequestInstall={(a) => (blockedForYou ? undefined : setReview(a))}
        onRetry={hub.reloadAll}
      />
      {reviewDialog}
    </>
  );
}

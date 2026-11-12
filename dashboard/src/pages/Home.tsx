// SPDX-License-Identifier: Apache-2.0
// Home launcher (IA §2.1) on @onemind/ui HomeScreen, fed by /v1/nodes, /v1/apps and /v1/actions.
// Widgets whose API is not on this hub yet (backups, updates, mesh) say which work stream brings
// them instead of showing made-up numbers.
import { useMemo, useState } from 'react';
import { HomeScreen, useOptionalCustomize, useToast, type ActionSummary, type HomeData, type HomeLayout, type HomeLoadable } from '@onemind/ui';
import { homeActivity, toActionSummary, toHomeApp, toHomeNode } from '../data/adapters';
import { errorText, useHub, type Hub } from '../data/hub';
import { homeLayoutStore } from '../data/prefs';
import type { Polled } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { useActivity, useShell } from '../shell/Shell';

/** Home's first layout here: only widgets this hub can feed. The rest are in the widget gallery. */
export const DASHBOARD_HOME_LAYOUT: HomeLayout = {
  version: 1,
  widgets: [
    { id: 'w-approvals', kind: 'approvals', size: 'M' },
    { id: 'w-system', kind: 'system', size: 'M' },
    { id: 'w-activity', kind: 'activity', size: 'M' },
  ],
  pinned: [],
};

const coming = (what: string, stream: string): HomeLoadable<never> => ({ state: 'error', error: 'not_available', message: `${what} come with ${stream}; this hub does not serve them yet.` });

function loadable<T, U>(p: Polled<T>, map: (d: T) => U): HomeLoadable<U> {
  if (p.data !== undefined) return { state: 'ready', data: map(p.data) };
  if (p.error) return { state: 'error', error: p.error.code, message: p.error.message };
  return { state: 'loading' };
}

export function homeData(hub: Hub, activity: ReturnType<typeof homeActivity>): HomeData {
  return {
    hub: { observed_at: hub.asOf ?? new Date(0).toISOString() },
    nodes: loadable(hub.nodes, (ns) => ns.map((n) => toHomeNode(n, hub.nodeStatus(n)))),
    apps: loadable(hub.apps, (as) => as.map((a) => toHomeApp(a))),
    approvals: hub.actions.data !== undefined ? { state: 'ready', data: hub.actionList.map(toActionSummary) } : loadable(hub.actions, () => [] as ActionSummary[]),
    activity: hub.actions.data !== undefined ? { state: 'ready', data: activity } : loadable(hub.actions, () => activity),
    backups: coming('Backups', 'CORE-BACKUP'),
    updates: coming('OS and app updates', 'CORE-UPDATE'),
    mesh: coming('Mesh links', 'CORE-FABRIC'),
    appWidgets: {},
    weather: null,
  };
}

export function Home() {
  const hub = useHub();
  const { principal } = useSignedIn();
  const shell = useShell();
  const toast = useToast();
  const customize = useOptionalCustomize();
  const person = principal?.id ?? 'me';
  const store = useMemo(() => homeLayoutStore(), []);
  const [layout, setLayout] = useState<HomeLayout>(() => store.load(person) ?? DASHBOARD_HOME_LAYOUT);
  const entries = useActivity();
  const data = homeData(hub, homeActivity(entries));

  const decide = (a: ActionSummary, how: 'approve' | 'deny') =>
    hub.decide(a.id, how).then(
      () => toast.show({ tone: how === 'approve' ? 'ok' : 'neutral', title: how === 'approve' ? 'Approved' : 'Denied', body: how === 'approve' ? 'The hub is applying it.' : 'Nothing changes.' }),
      (e: unknown) => {
        const { code, message } = errorText(e);
        toast.show({ tone: 'bad', title: `Could not ${how}`, body: `${message} (${code})` });
      },
    );

  return (
    <HomeScreen
      data={data}
      now={hub.now}
      timeZone={Intl.DateTimeFormat().resolvedOptions().timeZone}
      personName={principal?.kind === 'person' ? principal.id : undefined}
      layout={layout}
      onLayoutChange={(next) => {
        setLayout(next);
        store.save(person, next);
      }}
      wallpaper={customize && customize.prefs.wallpaper !== 'none' ? 'host' : 'tide'}
      canDecide={hub.canDecide === 'no' ? { allowed: false, reason: 'Only the owner can approve or deny.' } : { allowed: true }}
      onApprove={(a) => void decide(a, 'approve')}
      onDeny={(a) => void decide(a, 'deny')}
      busy={hub.busy}
      onOpenSearch={shell.openPalette}
      links={{
        approvals: href.approvals,
        nodes: href.nodes,
        activity: href.activity,
        backups: href.setting('backups'),
        updates: href.setting('updates'),
        mesh: href.nodes,
        apps: href.market,
        app: (id) => (hub.apps.data?.find((a) => a.id === id)?.installed ? href.manage(id) : href.app(id)),
        approval: (id) => href.approval(id),
      }}
    />
  );
}

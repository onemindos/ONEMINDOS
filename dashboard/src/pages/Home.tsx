// SPDX-License-Identifier: Apache-2.0
// Home launcher (IA §2.1) on @onemind/ui HomeScreen, fed by /v1/nodes, /v1/apps and /v1/actions.
// Backups, updates and mesh read /v1/backups/status, /v1/os/updates and /v1/mesh (data/homeExtras).
import { useMemo, useState } from 'react';
import { StateView, HomeScreen, useOptionalCustomize, useToast, type ActionSummary, type HomeData, type HomeLayout, type HomeLoadable } from '@onemind/ui';
import { useHomeExtras } from '../data/homeExtras';
import { homeActivity, toActionSummary, toHomeApp, toHomeNode } from '../data/adapters';
import { errorText, useHub, type Hub } from '../data/hub';
import { homeLayoutStore } from '../data/prefs';
import type { Polled } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { showsNav } from '../shell/roles';
import { useActivity, useShell } from '../shell/Shell';
import { SimpleHome } from './SimpleHome';

/** Home's first layout here: only widgets this hub can feed. The rest are in the widget gallery. */
export const DASHBOARD_HOME_LAYOUT: HomeLayout = {
  version: 1,
  widgets: [
    { id: 'w-approvals', kind: 'approvals', size: 'M' },
    { id: 'w-system', kind: 'system', size: 'M' },
    { id: 'w-activity', kind: 'activity', size: 'M' },
    { id: 'w-updates', kind: 'updates', size: 'S' },
    { id: 'w-backups', kind: 'backups', size: 'S' },
  ],
  pinned: [],
};

function loadable<T, U>(p: Polled<T>, map: (d: T) => U): HomeLoadable<U> {
  if (p.data !== undefined) return { state: 'ready', data: map(p.data) };
  if (p.error) return { state: 'error', error: p.error.code, message: p.error.message };
  return { state: 'loading' };
}

export function homeData(hub: Hub, activity: ReturnType<typeof homeActivity>, extras: Pick<HomeData, 'backups' | 'updates' | 'mesh'>): HomeData {
  return {
    hub: { observed_at: hub.asOf ?? new Date(0).toISOString() },
    nodes: loadable(hub.nodes, (ns) => ns.map((n) => toHomeNode(n, hub.nodeStatus(n)))),
    apps: loadable(hub.apps, (as) => as.map((a) => toHomeApp(a))),
    approvals: hub.actions.data !== undefined ? { state: 'ready', data: hub.actionList.map(toActionSummary) } : loadable(hub.actions, () => [] as ActionSummary[]),
    activity: hub.actions.data !== undefined ? { state: 'ready', data: activity } : loadable(hub.actions, () => activity),
    ...extras,
    appWidgets: {},
    weather: null,
  };
}

/** Child and guest get the simple Home; the Pro one is for owners and adults. Fail closed while the role is unknown. */
export function Home() {
  const shell = useShell();
  if (shell.view === 'simple') return <SimpleHome />;
  if (shell.view === 'unknown') return <StateView state="loading" what="Checking your role" skeleton="list" />;
  return <ProHome />;
}

function ProHome() {
  const hub = useHub();
  const { principal, person } = useSignedIn();
  const shell = useShell();
  const toast = useToast();
  const customize = useOptionalCustomize();
  const store = useMemo(() => homeLayoutStore(), []);
  const [layout, setLayout] = useState<HomeLayout>(() => store.load(person) ?? DASHBOARD_HOME_LAYOUT);
  const entries = useActivity();
  const apps = useMemo(() => hub.apps.data?.map((a) => toHomeApp(a)), [hub.apps.data]);
  const extras = useHomeExtras(apps, hub.asOf ?? new Date(0).toISOString());
  const data = homeData(hub, homeActivity(entries), extras);
  const pro = showsNav('nodes', shell.view);

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
      showDock={shell.layout === 'console'}
      links={{
        approvals: href.approvals,
        // Nodes and Backups are Pro screens (roles.ts): a guest or child gets no link to them.
        nodes: pro ? href.nodes : '',
        activity: href.activity,
        backups: pro ? href.backups : '',
        updates: href.updates,
        mesh: pro ? href.nodes : '',
        apps: href.market,
        app: (id) => (hub.apps.data?.find((a) => a.id === id)?.installed ? href.manage(id) : href.app(id)),
        approval: (id) => href.approval(id),
      }}
    />
  );
}

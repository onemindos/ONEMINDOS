// SPDX-License-Identifier: Apache-2.0
// Home launcher (IA §2.1) on @onemind/ui HomeScreen, fed by /v1/nodes, /v1/apps and /v1/actions.
// Backups, updates and mesh read /v1/backups/status, /v1/os/updates and /v1/mesh (data/homeExtras).
// On the desktop layout Home is the Atlas desktop itself (DesktopHome: a column of tiles on the
// wallpaper, windows over the rest); the Console layout keeps the launcher page (HomeScreen).
import { useMemo, useState, type ReactNode } from 'react';
import { DesktopHome, HomeScreen, StateView, useOptionalCustomize, useToast, type ActionSummary, type BackupStatus, type StorageStatus, type HomeData, type HomeLayout, type HomeLoadable } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useHomeExtras } from '../data/homeExtras';
import { homeActivity, toActionSummary, toHomeApp, toHomeNode } from '../data/adapters';
import { errorText, useHub, type Hub } from '../data/hub';
import { useHomeBackups } from '../data/homeBackups';
import { useDisplayName } from '../data/homeMe';
import { useBoxStatus } from '../data/homeStatus';
import { useHomeStorage } from '../data/homeStorage';
import { homeLayoutStore } from '../data/prefs';
import type { Polled } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { showsNav } from '../shell/roles';
import { useActivity, useShell } from '../shell/Shell';
import { HomeCommandBar } from './HomeCommandBar';
import { HomeHealth } from './HomeHealth';
import { SimpleHome } from './SimpleHome';
import { HomeRecent } from './HomeRecent';
import './home-desktop.css';

/**
 * Home's first layout: "Needs you" and System on top, then a trust tile, Storage and Backups for
 * people who may read them (two small tiles and one medium one fill the second row).
 * The raw activity log lives in the Activity window (and the widget gallery), not here.
 */
export function dashboardHomeLayout(pro: boolean): HomeLayout {
  return {
    version: 1,
    widgets: [
      { id: 'w-approvals', kind: 'approvals', size: 'M' },
      { id: 'w-system', kind: 'system', size: 'M' },
      ...(pro
        ? [
            { id: 'w-trust', kind: 'trust' as const, size: 'S' as const },
            { id: 'w-storage', kind: 'storage' as const, size: 'S' as const },
            { id: 'w-backups', kind: 'backups' as const, size: 'M' as const },
          ]
        : []),
    ],
    pinned: [],
  };
}

function loadable<T, U>(p: Polled<T>, map: (d: T) => U): HomeLoadable<U> {
  if (p.data !== undefined) return { state: 'ready', data: map(p.data) };
  if (p.error) return { state: 'error', error: p.error.code, message: p.error.message };
  return { state: 'loading' };
}

export function homeData(hub: Hub, activity: ReturnType<typeof homeActivity>, extras: Pick<HomeData, 'updates' | 'mesh'>, backups: HomeLoadable<BackupStatus>, storage?: HomeLoadable<StorageStatus>): HomeData {
  return {
    hub: { observed_at: hub.asOf ?? new Date(0).toISOString() },
    nodes: loadable(hub.nodes, (ns) => ns.map((n) => toHomeNode(n, hub.nodeStatus(n)))),
    apps: loadable(hub.apps, (as) => as.map((a) => toHomeApp(a))),
    approvals: hub.actions.data !== undefined ? { state: 'ready', data: hub.actionList.map((a) => toActionSummary(a, hub.appName)) } : loadable(hub.actions, () => [] as ActionSummary[]),
    activity: hub.actions.data !== undefined ? { state: 'ready', data: activity } : loadable(hub.actions, () => activity),
    backups,
    storage,
    updates: extras.updates,
    mesh: extras.mesh,
    appWidgets: {},
    weather: null,
  };
}

/** Child and guest get the simple Home; the Pro one is for owners and adults. Fail closed while the role is unknown. */
export function Home() {
  const shell = useShell();
  const customize = useOptionalCustomize();
  const { apps } = useHub();
  if (shell.view === 'unknown') return <StateView state="loading" what="Checking your role" skeleton="list" />;
  const commandBar = customize?.prefs.commandBar
    ? <HomeCommandBar openPalette={shell.openPalette} apps={shell.role === 'owner' ? apps.data ?? [] : []} />
    : undefined;
  return shell.view === 'simple' ? <SimpleHome commandBar={commandBar} /> : <ProHome commandBar={commandBar} />;
}

function ProHome({ commandBar }: { commandBar: ReactNode }) {
  const hub = useHub();
  const { person } = useSignedIn();
  const personName = useDisplayName();
  const shell = useShell();
  const toast = useToast();
  const customize = useOptionalCustomize();
  const store = useMemo(() => homeLayoutStore(), []);
  const pro = showsNav('nodes', shell.view);
  const [layout, setLayout] = useState<HomeLayout>(() => store.load(person) ?? dashboardHomeLayout(pro));
  const entries = useActivity();
  const backups = useHomeBackups(pro);
  const storage = useHomeStorage(pro);
  const apps = useMemo(() => hub.apps.data?.map((a) => toHomeApp(a)), [hub.apps.data]);
  const extras = useHomeExtras(apps, hub.asOf ?? new Date(0).toISOString());
  const boxStatus = useBoxStatus();
  const data = homeData(hub, homeActivity(entries), extras, backups.value, storage.value);

  const decide = (a: ActionSummary, how: 'approve' | 'deny') =>
    hub.decide(a.id, how).then(
      () => toast.show({ tone: how === 'approve' ? 'ok' : 'neutral', title: how === 'approve' ? 'Approved' : 'Denied', body: how === 'approve' ? 'The hub is applying it.' : 'Nothing changes.' }),
      (e: unknown) => {
        const { code, message } = errorText(e);
        const licence = e instanceof ApiError && e.reason === 'licence_unconfirmed';
        toast.show({ tone: 'bad', title: `Could not ${how}`, body: licence ? 'This app needs its licence accepted. Open Approvals to read it and confirm.' : `${message} (${code})` });
      },
    );

  const canDecide = hub.canDecide === 'no' ? { allowed: false as const, reason: 'Only the owner can approve or deny.' } : { allowed: true as const };
  const onRetry = () => {
    hub.reloadAll();
    void backups.reload();
    void storage.reload();
  };
  const onLayoutChange = (next: HomeLayout) => {
    setLayout(next);
    store.save(person, next);
  };
  const links = {
    approvals: href.approvals,
    // Nodes and Backups are Pro screens (roles.ts): a guest or child gets no link to them.
    nodes: pro ? href.nodes : '',
    activity: href.activity,
    backups: pro ? href.backups : '',
    updates: href.updates,
    mesh: pro ? href.nodes : '',
    apps: href.market,
    storage: pro ? href.storage : '',
    app: (id: string) => (hub.apps.data?.find((a) => a.id === id)?.installed ? href.manage(id) : href.app(id)),
    approval: (id: string) => href.approval(id),
  };

  if (shell.layout === 'desktop') {
    // IA §2.1 on the Atlas desktop: the greeting, then box health, then the tiles; recent visits last.
    return (
      <DesktopHome
        data={{ ...data, boxStatus }}
        now={hub.now}
        timeZone={Intl.DateTimeFormat().resolvedOptions().timeZone}
        personName={personName}
        layout={layout}
        onLayoutChange={onLayoutChange}
        defaultLayout={dashboardHomeLayout(pro)}
        canDecide={canDecide}
        onApprove={(a) => void decide(a, 'approve')}
        onDeny={(a) => void decide(a, 'deny')}
        busy={hub.busy}
        onRetry={onRetry}
        commandBar={commandBar}
        status={<HomeHealth pro={pro} status={boxStatus} />}
        footer={<HomeRecent />}
        links={links}
      />
    );
  }

  return (
    <HomeScreen
      data={{ ...data, boxStatus }}
      now={hub.now}
      timeZone={Intl.DateTimeFormat().resolvedOptions().timeZone}
      personName={personName}
      onRetry={onRetry}
      layout={layout}
      onLayoutChange={onLayoutChange}
      wallpaper={customize && customize.prefs.wallpaper !== 'none' ? 'host' : 'tide'}
      canDecide={canDecide}
      onApprove={(a) => void decide(a, 'approve')}
      onDeny={(a) => void decide(a, 'deny')}
      busy={hub.busy}
      commandBar={commandBar}
      // IA §2.1: the greeting first, then box health, the widgets and the apps; recent visits last.
      status={<HomeHealth pro={pro} status={boxStatus} />}
      footer={<HomeRecent />}
      onOpenSearch={shell.openPalette}
      showDock={shell.layout === 'console'}
      links={links}
    />
  );
}

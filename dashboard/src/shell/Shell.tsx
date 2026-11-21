// SPDX-License-Identifier: Apache-2.0
// The frame around every signed-in screen: the Desktop (DesktopShell: wallpaper desktop, windows,
// dock; the default, D-016) or the Console (@onemind/ui AppShell: sidebar, phone tab bar), the hub
// connection pill, the ⌘K palette, the notification bell and the jobs tray. In-app links from ui
// components are routed here, so the page never reloads (mock state and polls survive).
import { createContext, useContext, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  AppShell,
  Button,
  CommandPalette,
  FreshnessPill,

  NotificationBell,
  PaletteTrigger,
  buildPaletteCommands,
  formatAgo,
  pushRecentCommand,

  usePaletteHotkey,
  type NavItem,
  type PaletteCommand,
} from '@onemind/ui';
import { activityFrom, notificationsFrom, toActionSummary, toPaletteApp } from '../data/adapters';
import { ActionJobs } from './ActionJobs';
import { useHub } from '../data/hub';
import { useAppRequest } from './useAppRequest';
import { homeLayoutStore, personList } from '../data/prefs';
import { DesktopShell, type DockApp } from './DesktopShell';
import { useLayoutMode, type LayoutMode } from './layoutMode';
import { brand } from '../brand.generated';
import { useSignedIn } from '../session';
import { href, navId, toRoute } from './routes';
import { meRetryDelay, roleOf, showsNav, viewFor, type View } from './roles';
import { usePoll } from '../lib/hooks';

interface ShellApi {
  openPalette: () => void;
  /** Request an app action from anywhere, with the toasts; resolves to the action id. */
  requestApp: ReturnType<typeof useAppRequest>['requestApp'];
  /** Simple or Pro, from the signed-in role (roles.ts); 'unknown' until GET /v1/me answers. */
  view: View;
  /** Desktop (default) or Console, chosen per person (layoutMode.ts). */
  layout: LayoutMode;
}
const ShellCtx = createContext<ShellApi | null>(null);
export function useShell(): ShellApi {
  const s = useContext(ShellCtx);
  if (!s) throw new Error('useShell outside Shell');
  return s;
}

/** The contract's action types; anything else is shown as "coming", never sent. */
const CONTRACT_TYPES = new Set(['app.install', 'app.remove', 'app.start', 'app.stop', 'app.restart', 'app.update']);

export function Shell({ children }: { children: ReactNode }) {
  const hub = useHub();
  const { principal, person, signOut, mock, api: client } = useSignedIn();
  const navigate = useNavigate();
  const location = useLocation();
  const { requestApp, reviewDialog } = useAppRequest();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const readStore = useMemo(() => personList(person, 'notifications.read'), [person]);
  const recentStore = useMemo(() => personList(person, 'palette.recent', 8), [person]);
  const [read, setRead] = useState(() => new Set(readStore.load()));
  const [recent, setRecent] = useState(() => recentStore.load());

  const [layout, setLayout] = useLayoutMode(person);

  usePaletteHotkey(() => setPaletteOpen(true));

  // A real gateway session does not carry the role, so ask GET /v1/me once. If that fails the
  // view falls back to Simple (fail closed): the Pro screens are offered only to a known role.
  const me = usePoll(() => (principal ? Promise.resolve(null) : client.me()), 0);
  const role = roleOf(principal, me.data ?? undefined);
  const view = viewFor(role === undefined && me.error ? null : role);
  // A failed lookup is retried with backoff, then slowly, so a network hiccup does not leave an
  // owner in the Simple view until a reload. Stops once /v1/me answers.
  const meTries = useRef(0);
  const { error: meError, reload: meReload } = me;
  useEffect(() => {
    if (!meError) {
      meTries.current = 0;
      return;
    }
    const id = window.setTimeout(() => void meReload(), meRetryDelay(meTries.current++));
    return () => window.clearTimeout(id);
  }, [meError, meReload]);

  const go = (link: string) => {
    const to = toRoute(link);
    if (to) navigate(to);
  };


  const nodes = hub.nodes.data ?? [];
  const apps = hub.apps.data ?? [];
  const pending = hub.actionList.filter((a) => a.state === 'awaiting_approval');
  const notifications = useMemo(
    () => notificationsFrom(hub.actionList, nodes.map((n) => ({ ...n, status: hub.nodeStatus(n) })), hub.appName, read),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hub.actionList, hub.nodes.data, hub.appName, read, hub.now - (hub.now % 10_000)],
  );
  const markRead = (ids: string[], value: boolean) => {
    const next = new Set(read);
    ids.forEach((id) => (value ? next.add(id) : next.delete(id)));
    setRead(next);
    readStore.save([...next]);
  };

  const commands = useMemo(
    () =>
      buildPaletteCommands({
        now: hub.now,
        apps: apps.map(toPaletteApp),
        nodes: nodes.map((n) => ({ ...n, status: hub.nodeStatus(n) })),
        pending: pending.map(toActionSummary),
        canApprove: hub.canDecide !== 'no',
      }).filter((c) => paletteShows(c, view)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hub.apps.data, hub.nodes.data, hub.actionList, hub.canDecide, view],
  );
  const runCommand = (c: PaletteCommand) => {
    setPaletteOpen(false);
    const r = pushRecentCommand(recent, c.id);
    setRecent(r);
    recentStore.save(r);
    if (c.request) {
      const appId = String(c.request.params.app_id ?? '');
      if (CONTRACT_TYPES.has(c.request.type) && appId) void requestApp(c.request.type as Parameters<typeof requestApp>[0], appId);
    } else if (c.href) go(c.href);
  };


  const waiting = pending.length;
  const allNav: NavItem[] = [
    { id: 'home', label: 'Home', href: href.home, icon: 'home', primary: true },
    { id: 'market', label: 'Market', href: href.market, icon: 'apps', primary: true },
    { id: 'approvals', label: 'Approvals', href: href.approvals, icon: 'approvals', primary: true, badge: waiting, badgeLabel: `${waiting} waiting` },
    { id: 'activity', label: 'Activity', href: href.activity, icon: 'activity', primary: true },
    { id: 'installed', label: 'Installed', href: href.installed, icon: 'check', group: 'Your box' },
    { id: 'nodes', label: 'Nodes', href: href.nodes, icon: 'nodes', group: 'Your box' },
    { id: 'machines', label: 'Machines', href: href.machines, icon: 'monitor', group: 'Your box' },
    { id: 'alerts', label: 'Alerts', href: href.alerts, icon: 'bell', group: 'Your box' },
    { id: 'storage', label: 'Storage', href: href.storage, icon: 'storage', group: 'Your box' },
    { id: 'backups', label: 'Backups', href: href.backups, icon: 'backups', group: 'Your box' },
    { id: 'automation', label: 'Automation', href: href.automation, icon: 'clock', group: 'Your box' },
    { id: 'updates', label: 'OS updates', href: href.updates, icon: 'updates', group: 'Your box' },
    { id: 'settings', label: 'Settings', href: href.settings, icon: 'settings', group: 'Your box' },
    { id: 'coming', label: 'Coming soon', href: href.coming, icon: 'info', group: 'Your box' },
    { id: 'control-hub', label: 'Control Hub', href: href.controlHub, icon: 'hub', group: 'System' },
    { id: 'agents', label: 'AI & Agents', href: href.agents, icon: 'agent', group: 'System' },
  ];
  const nav = allNav.filter((item) => showsNav(item.id, view));

  // Route plain in-app links from ui components through the router (no reload).
  const onClickCapture = (e: MouseEvent<HTMLDivElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = (e.target as HTMLElement).closest('a');
    if (!a || a.target || a.hasAttribute('download')) return;
    const raw = a.getAttribute('href') ?? '';
    if (raw === '#om-main' || raw.startsWith('#om')) return;
    const to = toRoute(raw);
    if (!to) return;
    e.preventDefault();
    navigate(to);
  };

  const status =
    hub.freshness === 'unknown' ? (
      <FreshnessPill state="unknown" detail="connecting to the hub" />
    ) : (
      <FreshnessPill state={hub.freshness} detail={hub.freshness === 'live' ? 'hub answering' : `hub last answered ${formatAgo(hub.ageS ?? 0)}`} />
    );

  const boxName = hub.instance.data?.name ?? brand.shortName;
  const bell = (
    <NotificationBell
      items={notifications}
      now={hub.now}
      state={hub.freshness === 'stale' || hub.freshness === 'offline' ? hub.freshness : 'ready'}
      ageSeconds={hub.ageS}
      onRetry={hub.reloadAll}
      onOpen={(n) => {
        markRead([n.id], true);
        go(n.href);
      }}
      onSetRead={markRead}
      onReadAll={() => markRead(notifications.map((n) => n.id), true)}
      allHref={href.activity}
      settingsHref={href.setting('notifications')}
    />
  );
  const account = (
    <>
      <span className="dash-hide-compact">
        <PaletteTrigger onOpen={() => setPaletteOpen(true)} label="Search" />
      </span>
      {bell}
      {mock && <span className="dash-demo-flag">Demo data</span>}
      {principal && (
        <span className="dash-who dash-hide-compact">
          {principal.id} <span className="om-hint">({principal.kind === 'agent' ? 'agent' : principal.role})</span>
        </span>
      )}
      <Button size="sm" variant="ghost" onClick={() => setLayout('desktop')} title="Switch to the desktop layout">
        Desktop view
      </Button>
      <Button size="sm" variant="ghost" onClick={signOut}>
        Sign out
      </Button>
    </>
  );
  const api: ShellApi = { openPalette: () => setPaletteOpen(true), requestApp, view, layout };

  // Apps pinned on Home go in the dock (Home hides its own dock on the desktop).
  const pinnedIds = layout === 'desktop' ? (homeLayoutStore().load(person)?.pinned ?? []) : [];
  const dockApp = (a: (typeof apps)[number]): DockApp => ({ id: a.id, name: a.name ?? a.id, icon: a.icon, href: a.installed ? href.manage(a.id) : href.app(a.id) });
  const pinned: DockApp[] = pinnedIds.flatMap((id) => {
    const a = apps.find((x) => x.id === id);
    return a ? [dockApp(a)] : [];
  });
  const installedApps: DockApp[] = layout === 'desktop' ? apps.filter((a) => a.installed).map(dockApp) : [];
  return (
    <ShellCtx.Provider value={api}>
      <div onClickCapture={onClickCapture} className={layout === 'desktop' ? 'dash-root dash-desktop' : 'dash-root'}>
        {layout === 'desktop' ? (
          <DesktopShell
            boxName={boxName}
            nav={nav}
            current={navId(location.pathname)}
            status={status}
            bell={bell}
            pinned={pinned}
            apps={installedApps}
            now={hub.now}
            timeZone={Intl.DateTimeFormat().resolvedOptions().timeZone}
            person={principal ? { id: principal.id, role: principal.kind === 'agent' ? 'agent' : principal.role } : undefined}
            demo={mock}
            onSearch={() => setPaletteOpen(true)}
            onConsoleView={() => setLayout('console')}
            onSignOut={signOut}
          >
            {children}
          </DesktopShell>
        ) : (
          <AppShell boxName={boxName} nav={nav} current={navId(location.pathname)} status={status} account={account}>
            {children}
          </AppShell>
        )}
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          commands={commands}
          onRun={runCommand}
          recent={recent}
          state={hub.freshness === 'stale' || hub.freshness === 'offline' ? hub.freshness : hub.freshness === 'unknown' ? 'loading' : 'ready'}
          ageSeconds={hub.ageS}
        />
        <ActionJobs />
        {reviewDialog}
      </div>
    </ShellCtx.Provider>
  );
}

/** A palette command is offered when it leads to a screen this view shows (Pro screens: roles.ts). */
export function paletteShows(c: PaletteCommand, view: View): boolean {
  if (!c.href) return true;
  const to = toRoute(c.href);
  return to === undefined || showsNav(navId(to.split('?')[0] ?? '/'), view);
}

/** Activity entries are needed by Home and Activity; computed once per actions answer. */
export function useActivity() {
  const hub = useHub();
  return useMemo(() => activityFrom(hub.actionList, hub.appName), [hub.actionList, hub.appName]);
}

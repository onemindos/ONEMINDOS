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
  useOptionalCustomize,
  useToast,

  type NavItem,
  type PaletteCommand,
} from '@onemind/ui';
import { isServerId, mergeNotifications, SERVER_PREFIX } from '../data/notificationFeed';
import { useNotificationFeed } from '../data/useNotificationFeed';
import { useDownloadToasts } from '../data/useDownloadToasts';
import { useTipSearch } from '../data/useTipSearch';
import { activityFrom, notificationsFrom, toActionSummary, toPaletteApp } from '../data/adapters';
import { ActionJobs, jobsStackStyle } from './ActionJobs';
import { useHub } from '../data/hub';
import { useAppRequest } from './useAppRequest';
import { useRecordVisit } from '../data/homeRecent';
import { homeLayoutStore, personList } from '../data/prefs';
import { useKeymap } from './keys/useKeymap';
import { DesktopShell, type DockApp } from './DesktopShell';
import { fleetCounts } from './StatusStrip';
import { useLayoutMode, type LayoutMode } from './layoutMode';
import { QuickSettings } from './quick/QuickSettings';
import { effectiveView, useViewChoice } from './quick/viewPref';
import { brand } from '../brand.generated';
import { useSignedIn } from '../session';
import { navItems } from '../screens/registry';
import { href, navId, toRoute } from './routes';
import { decideState, meRetryDelay, roleOf, showsNav, viewFor, type View } from './roles';
import { usePoll } from '../lib/hooks';
import { useDisplayName } from '../data/homeMe';
import { useIdleLock, useIdleLockPreference } from './lock/state';

interface ShellApi {
  openPalette: () => void;
  /** Request an app action from anywhere, with the toasts; resolves to the action id. */
  requestApp: ReturnType<typeof useAppRequest>['requestApp'];
  /** Simple or Pro, from the signed-in role (roles.ts); 'unknown' until GET /v1/me answers. */
  view: View;
  /** The signed-in role ('child', 'guest', ...), null for an agent; undefined until known. */
  role: string | null | undefined;
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
  const { principal, account: signedInAccount, person, signOut, lock, mock, api: client } = useSignedIn();
  const navigate = useNavigate();
  const location = useLocation();
  const { requestApp, reviewDialog } = useAppRequest();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [tipQuery, setTipQuery] = useState('');
  const tipResults: PaletteCommand[] = useTipSearch(paletteOpen ? tipQuery : '').map(tip => ({
    ...tip, id: `tip:${tip.id}`, group: 'Tips', icon: 'info',
  }));
  const [jobsShown, setJobsShown] = useState(false);
  const readStore = useMemo(() => personList(person, 'notifications.read'), [person]);
  const recentStore = useMemo(() => personList(person, 'palette.recent', 8), [person]);
  const [read, setRead] = useState(() => new Set(readStore.load()));
  const [recent, setRecent] = useState(() => recentStore.load());

  const [layout, setLayout] = useLayoutMode(person);
  // The run bar (final design 09) is the person's Appearance choice, off by default.
  const runBar = useOptionalCustomize()?.prefs.commandBar === true;

  useKeymap({ palette: () => setPaletteOpen(true) });

  // A real gateway session does not carry the role, so ask GET /v1/me once. If that fails the
  // view falls back to Simple (fail closed): the Pro screens are offered only to a known role.
  const me = usePoll(() => (principal ? Promise.resolve(null) : client.me()), 0);
  const displayName = useDisplayName();
  const role = roleOf(principal, me.data ?? undefined);
  // The role decides Pro; the person may narrow it to Simple (quick settings), never widen it.
  const [viewChoice, setViewChoice] = useViewChoice(person);
  const view = effectiveView(viewFor(role === undefined && me.error ? null : role), viewChoice);
  const recordVisit = useRecordVisit(view, role);
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
    if (!to) return false;
    recordVisit(to);
    navigate(to);
    return true;
  };


  const nodes = hub.nodes.data ?? [];
  const apps = hub.apps.data ?? [];
  const pending = hub.actionList.filter((a) => a.state === 'awaiting_approval');
  const feed = useNotificationFeed();
  const toast = useToast();
  // #693: a browser download that passed quarantine and reached Files shows once as a toast.
  useDownloadToasts(feed.notifications, (t) => toast.show({ tone: 'ok', ...t }), () => navigate('/files'));
  const notifications = useMemo(
    () => mergeNotifications(feed.notifications, feed.alerts, notificationsFrom(hub.actionList, nodes.map((n) => ({ ...n, status: hub.nodeStatus(n) })), hub.appName, read), read),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [feed.notifications, feed.alerts, hub.actionList, hub.nodes.data, hub.appName, read, hub.now - (hub.now % 10_000)],
  );
  // Read state: a hub notification is also marked read on the hub (it follows the person to every
  // device; the hub has no "unread", so un-reading is this browser only). Alerts and derived facts
  // are remembered in this browser.
  const remember = (ids: string[], value: boolean) => {
    const next = new Set(read);
    ids.forEach((id) => (value ? next.add(id) : next.delete(id)));
    setRead(next);
    readStore.save([...next]);
  };
  const markRead = (ids: string[], value: boolean) => {
    const hubIds = ids.filter(isServerId);
    if (value && hubIds.length) void Promise.allSettled(hubIds.map((id) => client.markRead(id.slice(SERVER_PREFIX.length)))).then(feed.reload);
    remember(ids, value);
  };
  const readAll = () => {
    void client.markAllRead().then(feed.reload, () => undefined);
    remember(notifications.map((n) => n.id), true);
  };

  const commands = useMemo(
    () =>
      buildPaletteCommands({
        now: hub.now,
        apps: apps.map(toPaletteApp),
        nodes: nodes.map((n) => ({ ...n, status: hub.nodeStatus(n) })),
        pending: pending.map((a) => toActionSummary(a, hub.appName)),
        canApprove: decideState(role, hub.canDecide) !== 'no',
      }).filter((c) => paletteShows(c, view, role)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hub.apps.data, hub.nodes.data, hub.actionList, hub.canDecide, view, role],
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
  const allNav: NavItem[] = navItems(waiting);
  // Troubleshoot is owner-only on the hub (system:admin); hidden once we know this principal is not an owner.
  const nav = allNav.filter((item) => showsNav(item.id, view, role) && !(item.id === 'troubleshoot' && hub.canDecide === 'no'));

  // Route plain in-app links from ui components through the router (no reload).
  const onClickCapture = (e: MouseEvent<HTMLDivElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = (e.target as HTMLElement).closest('a');
    if (!a || a.target || a.hasAttribute('download')) return;
    const raw = a.getAttribute('href') ?? '';
    if (raw === '#om-main' || raw.startsWith('#om')) return;
    if (go(raw)) e.preventDefault();
  };

  const status =
    hub.freshness === 'unknown' ? (
      <FreshnessPill state="unknown" detail="connecting to the hub" />
    ) : (
      <FreshnessPill state={hub.freshness} detail={hub.freshness === 'live' ? 'hub answering' : `hub last answered ${formatAgo(hub.ageS ?? 0)}`} />
    );

  const boxName = hub.instance.data?.name ?? brand.shortName;
  const knownPerson = signedInAccount ?? me.data?.principal ?? principal;
  const canLock = knownPerson?.kind !== 'agent';
  const lockNow = () => lock({ boxName, waiting, ...(displayName ? { person: displayName } : {}) });
  const idle = useIdleLockPreference(knownPerson?.kind === 'person' ? knownPerson.id : undefined, role === 'owner');
  useIdleLock(canLock && knownPerson ? idle : 0, lockNow);
  const bell = (
    <>
    <QuickSettings role={role} view={view} viewChoice={viewChoice} onViewChoice={setViewChoice} />
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
      onReadAll={readAll}
      allHref={href.activity}
      settingsHref={href.setting('notifications')}
    />
    </>
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
      {canLock && <Button size="sm" variant="ghost" onClick={lockNow}>Lock now</Button>}
      <Button size="sm" variant="ghost" onClick={signOut}>
        Sign out
      </Button>
    </>
  );
  const api: ShellApi = { openPalette: () => setPaletteOpen(true), requestApp, view, role, layout };

  // Apps pinned on Home go in the dock (Home hides its own dock on the desktop).
  const pinnedIds = layout === 'desktop' ? (homeLayoutStore().load(person)?.pinned ?? []) : [];
  const dockApp = (a: (typeof apps)[number]): DockApp => ({ id: a.id, name: a.name ?? a.id, icon: a.icon, href: a.installed ? href.manage(a.id) : href.app(a.id) });
  const pinned: DockApp[] = pinnedIds.flatMap((id) => {
    const a = apps.find((x) => x.id === id);
    return a ? [dockApp(a)] : [];
  });
  const installedApps: DockApp[] = layout === 'desktop' ? apps.filter((a) => a.installed).map(dockApp) : [];
  // The strip's counts: real answers only. Nothing is drawn before GET /v1/nodes and GET /v1/actions first answer.
  const fleet = hub.nodes.data ? fleetCounts(nodes.map((n) => hub.nodeStatus(n))) : undefined;
  const waitingKnown = hub.actions.data !== undefined ? waiting : undefined;
  const machines = nav.some((n) => n.id === 'nodes') ? nodes.map((n) => ({ id: n.node_id, name: n.hostname, status: hub.nodeStatus(n) })) : [];
  const waitingRequests = pending.map((a) => ({ id: a.id, type: a.type, appId: appIdOf(a.params) }));
  return (
    <ShellCtx.Provider value={api}>
      <div onClickCapture={onClickCapture} className={layout === 'desktop' ? 'dash-root dash-desktop' : 'dash-root'} data-jobs={jobsShown ? '' : undefined} style={jobsStackStyle(jobsShown)}>
        {layout === 'desktop' ? (
          <DesktopShell
            boxName={boxName}
            nav={nav}
            current={navId(location.pathname)}
            status={status}
            bell={bell}
            pinned={pinned}
            apps={installedApps}
            fleet={fleet}
            waiting={waitingKnown}
            machines={machines}
            commands={commands}
            onRunCommand={runCommand}
            onOpen={(link) => void go(link)}
            runBar={runBar}
            waitingRequests={waitingRequests}
            now={hub.now}
            timeZone={Intl.DateTimeFormat().resolvedOptions().timeZone}
            person={principal ? { id: principal.id, role: principal.kind === 'agent' ? 'agent' : principal.role } : undefined}
            displayName={displayName}
            demo={mock}
            onSearch={() => setPaletteOpen(true)}
            onConsoleView={() => setLayout('console')}
            onSignOut={signOut}
            onLock={canLock ? lockNow : undefined}
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
          onSearch={setTipQuery}
          tipResults={tipResults}
          tipQuery={tipQuery}
          onRun={runCommand}
          recent={recent}
          state={hub.freshness === 'stale' || hub.freshness === 'offline' ? hub.freshness : hub.freshness === 'unknown' ? 'loading' : 'ready'}
          ageSeconds={hub.ageS}
        />
        {view !== 'simple' && <ActionJobs onShown={setJobsShown} />}
        {reviewDialog}
      </div>
    </ShellCtx.Provider>
  );
}

/** The app a request is about, when it is an app request. */
function appIdOf(params: unknown): string | undefined {
  const id = (params as { app_id?: unknown } | null | undefined)?.app_id;
  return typeof id === 'string' ? id : undefined;
}

/** A palette command is offered when it leads to a screen this view shows (Pro screens: roles.ts). */
export function paletteShows(c: PaletteCommand, view: View, role?: string | null): boolean {
  if (!c.href) return true;
  const to = toRoute(c.href);
  return to === undefined || showsNav(navId(to.split('?')[0] ?? '/'), view, role);
}

/** Activity entries are needed by Home and Activity; computed once per actions answer. */
export function useActivity() {
  const hub = useHub();
  return useMemo(() => activityFrom(hub.actionList, hub.appName), [hub.actionList, hub.appName]);
}

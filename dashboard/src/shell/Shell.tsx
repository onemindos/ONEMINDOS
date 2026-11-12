// SPDX-License-Identifier: Apache-2.0
// The frame around every signed-in screen: @onemind/ui AppShell (sidebar, phone tab bar), the hub
// connection pill, the ⌘K palette, the notification bell and the jobs tray. In-app links from ui
// components are routed here, so the page never reloads (mock state and polls survive).
import { createContext, useContext, useMemo, useState, type MouseEvent, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  AppShell,
  Button,
  CommandPalette,
  FreshnessPill,
  JobsTray,
  NotificationBell,
  PaletteTrigger,
  buildPaletteCommands,
  formatAgo,
  pushRecentCommand,
  toastForRequestError,
  useToast,
  usePaletteHotkey,
  type NavItem,
  type PaletteCommand,
} from '@onemind/ui';
import { activityFrom, isActive, notificationsFrom, toActionSummary, toJob, toPaletteApp } from '../data/adapters';
import { errorText, useHub } from '../data/hub';
import { personList } from '../data/prefs';
import { useSignedIn } from '../session';
import { href, navId, toRoute } from './routes';

interface ShellApi {
  openPalette: () => void;
  /** Request an app action from anywhere, with the toasts; resolves to the action id. */
  requestApp: (type: 'app.install' | 'app.remove', appId: string) => Promise<string | undefined>;
}
const ShellCtx = createContext<ShellApi | null>(null);
export function useShell(): ShellApi {
  const s = useContext(ShellCtx);
  if (!s) throw new Error('useShell outside Shell');
  return s;
}

/** The contract's action types; anything else is shown as "coming", never sent. */
const CONTRACT_TYPES = new Set(['app.install', 'app.remove']);

export function Shell({ children }: { children: ReactNode }) {
  const hub = useHub();
  const { principal, person, signOut, mock } = useSignedIn();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const readStore = useMemo(() => personList(person, 'notifications.read'), [person]);
  const recentStore = useMemo(() => personList(person, 'palette.recent', 8), [person]);
  const [read, setRead] = useState(() => new Set(readStore.load()));
  const [recent, setRecent] = useState(() => recentStore.load());
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  usePaletteHotkey(() => setPaletteOpen(true));

  const go = (link: string) => {
    const to = toRoute(link);
    if (to) navigate(to);
  };

  const requestApp = async (type: 'app.install' | 'app.remove', appId: string) => {
    const name = hub.appName(appId);
    const title = `${type === 'app.install' ? 'Install' : 'Remove'} ${name}`;
    try {
      const a = await hub.request(type, appId);
      toast.show({ tone: 'info', title: 'Request sent', body: `${title}. It waits in Approvals until the owner decides.`, action: { label: 'View', onClick: () => navigate(href.approval(a.id)) } });
      return a.id;
    } catch (e) {
      const { code, message } = errorText(e);
      toast.show(toastForRequestError(title, code, message));
      return undefined;
    }
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
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hub.apps.data, hub.nodes.data, hub.actionList, hub.canDecide],
  );
  const runCommand = (c: PaletteCommand) => {
    setPaletteOpen(false);
    const r = pushRecentCommand(recent, c.id);
    setRecent(r);
    recentStore.save(r);
    if (c.request) {
      const appId = String(c.request.params.app_id ?? '');
      if (CONTRACT_TYPES.has(c.request.type) && appId) void requestApp(c.request.type as 'app.install' | 'app.remove', appId);
      else toast.show({ tone: 'neutral', title: `${c.title}: not on this hub yet`, body: `${c.request.type} comes with the app lifecycle actions of contract §12.5. Nothing was sent.` });
    } else if (c.href) go(c.href);
  };

  const jobs = hub.actionList
    .filter((a) => a.type === 'app.install' && !dismissed.has(a.id) && (isActive(a) || Date.parse(a.updated_at ?? '') > hub.now - 60_000))
    .map((a) => toJob(a, hub.appName(a.params.app_id)));

  const waiting = pending.length;
  const nav: NavItem[] = [
    { id: 'home', label: 'Home', href: href.home, icon: 'home', primary: true },
    { id: 'market', label: 'Market', href: href.market, icon: 'apps', primary: true },
    { id: 'approvals', label: 'Approvals', href: href.approvals, icon: 'approvals', primary: true, badge: waiting, badgeLabel: `${waiting} waiting` },
    { id: 'activity', label: 'Activity', href: href.activity, icon: 'activity', primary: true },
    { id: 'installed', label: 'Installed', href: href.installed, icon: 'check', group: 'Your box' },
    { id: 'nodes', label: 'Nodes', href: href.nodes, icon: 'nodes', group: 'Your box' },
    { id: 'settings', label: 'Settings', href: href.settings, icon: 'settings', group: 'Your box' },
  ];

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

  const boxName = hub.instance.data?.name ?? 'OneMind';
  const api: ShellApi = { openPalette: () => setPaletteOpen(true), requestApp };
  return (
    <ShellCtx.Provider value={api}>
      <div onClickCapture={onClickCapture} className="dash-root">
        <AppShell
          boxName={boxName}
          nav={nav}
          current={navId(location.pathname)}
          status={status}
          account={
            <>
              <span className="dash-hide-compact">
                <PaletteTrigger onOpen={() => setPaletteOpen(true)} label="Search" />
              </span>
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
              {mock && <span className="dash-demo-flag">Demo data</span>}
              {principal && (
                <span className="dash-who dash-hide-compact">
                  {principal.id} <span className="om-hint">({principal.kind === 'agent' ? 'agent' : principal.role})</span>
                </span>
              )}
              <Button size="sm" variant="ghost" onClick={signOut}>
                Sign out
              </Button>
            </>
          }
        >
          {children}
        </AppShell>
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          commands={commands}
          onRun={runCommand}
          recent={recent}
          state={hub.freshness === 'stale' || hub.freshness === 'offline' ? hub.freshness : hub.freshness === 'unknown' ? 'loading' : 'ready'}
          ageSeconds={hub.ageS}
        />
        <JobsTray jobs={jobs} now={hub.now} onDismiss={(id) => setDismissed((d) => new Set(d).add(id))} />
      </div>
    </ShellCtx.Provider>
  );
}

/** Activity entries are needed by Home and Activity; computed once per actions answer. */
export function useActivity() {
  const hub = useHub();
  return useMemo(() => activityFrom(hub.actionList, hub.appName), [hub.actionList, hub.appName]);
}

// SPDX-License-Identifier: Apache-2.0
// The desktop frame (D-016): no sidebar. "/" is the wallpaper desktop (Home); every other screen
// opens as a window over the wallpaper, with a back button for nested pages, a close button and
// Esc back to the desktop. A slim menu bar carries the OneMind mark, the hub clock and state,
// search, the bell and the person menu, plus the Atlas status strip: fresh/stale/offline machine counts and the
// needs-you chip (StatusStrip.tsx). The dock (dock.ts) starts with the OneMind logo tile, which opens the launcher
// (Launchpad.tsx, or Ctrl/⌘ + /), then the pinned places, running windows, pinned apps and the optional run bar.
// Pattern studied in umbrelOS 2.0.1 (PolyForm NC: no code, asset or text copied;
// docs/learning/umbrelos-2-teardown.md). OneMind's own look (founder picks 2026-11-21): today's logo, Atlas's
// muted tiles, status first, approvals one click away.
// Links are plain anchors: Shell's click handler routes them without a page reload.
import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { flushSync } from 'react-dom';
import { WindowFrame } from './wm/WindowFrame';
import { useWindows } from './wm/useWindows';
import { WORKSPACES, onWorkspace, position, toggleMax } from './wm/store';
import { LAYOUT_LABELS, nextLayout } from './wm/tiling';
import { useKeymap } from './keys/useKeymap';
import { ShortcutSheet } from './keys/ShortcutSheet';
import { routeFor, ScreenRoutes } from './wm/ScreenRoutes';
import './wm/wm.css';
import { BrandMark, Icon, useOptionalCustomize, type NavItem, type PaletteCommand } from '@onemind/ui';
import { Launchpad } from './Launchpad';
import type { LauncherMachine } from './launcher';
import { dockOrder, dockSplit } from './dock';
import { orderDock } from './dockOrder';
import { DockApps } from './DockApps';
import { RunBar, type WaitingRequest } from './RunBar';
import { FleetCountsView, NeedsYouChip, type FleetCounts } from './StatusStrip';
import { overlayOpen } from './overlay';
import { Badge, ScreenTile } from './tiles';
export { dockSplit } from './dock';
import { formatDate } from '../i18n';
import './desktop.css';
import { trackBarHeight } from './trackBarHeight';

export interface DockApp {
  id: string;
  name: string;
  icon?: string | null;
  href: string;
}

export interface DesktopPerson {
  id: string;
  role: string;
}

export interface DesktopShellProps {
  boxName: string;
  /** Hub connection state (a FreshnessPill). */
  status?: ReactNode;
  /** The notification bell. */
  bell?: ReactNode;
  nav: NavItem[];
  /** Nav id of the current route ('home' = the desktop). */
  current: string;
  /** Apps pinned on Home, in the dock after the screens. */
  pinned?: DockApp[];
  /** Installed apps, listed in the launcher. */
  apps?: DockApp[];
  /** Machine counts by state for the strip; undefined until GET /v1/nodes answers (nothing is drawn). */
  fleet?: FleetCounts;
  /** Requests awaiting a decision, for the needs-you chip; undefined until GET /v1/actions answers. */
  waiting?: number;
  /** Machines for the launcher (empty when this person cannot see Nodes). */
  machines?: LauncherMachine[];
  /** The palette's commands, for the launcher's command lines and the run bar. */
  commands?: PaletteCommand[];
  /** Run a palette command: open its screen or file its reviewed request. */
  onRunCommand?: (c: PaletteCommand) => void;
  /** Open an in-app link (the run bar's "already waiting" request). */
  onOpen?: (href: string) => void;
  /** The run bar in the dock (Settings > Appearance; off by default). */
  runBar?: boolean;
  /** Requests already waiting, so the run bar opens one instead of filing it twice. */
  waitingRequests?: WaitingRequest[];
  /** Hub clock (ms) and time zone, for the menu-bar clock. */
  now: number;
  timeZone: string;
  person?: DesktopPerson;
  /** The greeted first name, when known: its initial fills the avatar while the account is still loading. */
  displayName?: string;
  demo?: boolean;
  onSearch: () => void;
  onConsoleView: () => void;
  onSignOut: () => void;
  onLock?: () => void;
  children: ReactNode;
}

/** Short screens (a few facts and one action) open in a narrow window instead of a wide, mostly empty one. */
export const COMPACT_WINDOWS: ReadonlySet<string> = new Set(['storage', 'backups']);

/** A path one level up inside the same screen ("/market/x" → "/market"), or null at the top. */
export function parentPath(pathname: string): string | null {
  const parts = pathname.split('/').filter(Boolean);
  return parts.length > 1 ? `/${parts.slice(0, -1).join('/')}` : null;
}

function Clock({ now, timeZone }: { now: number; timeZone: string }) {
  const d = new Date(now);
  const day = formatDate(d, { weekday: 'short', month: 'short', day: 'numeric', timeZone });
  const time = formatDate(d, { hour: 'numeric', minute: '2-digit', timeZone });
  return (
    <time className="dsk-clock" dateTime={d.toISOString()} title="Hub time">
      <span className="dsk-clock-day">{day}</span> {time}
    </time>
  );
}

/** The name's initial when a name is known, else the account id's, else "?". */
export function avatarInitial(displayName?: string, id?: string): string {
  return (Array.from((displayName ?? '').trim()[0] ? displayName!.trim() : (id ?? '').trim())[0] ?? '?').toUpperCase();
}

/** `usageHref`: on a phone the Live usage icon leaves the menu bar (it no longer fits) and lives here instead. */
function PersonMenu({ person, displayName, demo, onConsoleView, onSignOut, onLock, usageHref }: Pick<DesktopShellProps, 'person' | 'displayName' | 'demo' | 'onConsoleView' | 'onSignOut' | 'onLock'> & { usageHref?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) {
        if (e instanceof KeyboardEvent) e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);
  const initial = avatarInitial(displayName, person?.id);
  return (
    <div className="dsk-person" ref={ref}>
      <button type="button" className="dsk-avatar" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden="true">{initial}</span>
        <span className="om-visually-hidden">{person ? `Account: ${person.id}` : 'Account'}</span>
      </button>
      {open && (
        <div id={menuId} className="dsk-menu" role="group" aria-label="Account">
          {person && (
            <div className="dsk-menu-who">
              <span className="dsk-avatar dsk-avatar-lg" aria-hidden="true">
                {initial}
              </span>
              <span>
                <strong>{person.id}</strong>
                <span className="om-hint">{person.role}</span>
              </span>
            </div>
          )}
          {demo && <p className="dsk-menu-demo">Demo data</p>}
          <a className="dsk-menu-item" href="/settings" onClick={() => setOpen(false)}>
            <Icon name="settings" size={16} /> Settings
          </a>
          {usageHref && (
            <a className="dsk-menu-item dsk-phone-only" href={usageHref} onClick={() => setOpen(false)}>
              <Icon name="gauge" size={16} /> Live usage
            </a>
          )}
          <button
            type="button"
            className="dsk-menu-item"
            onClick={() => {
              setOpen(false);
              onConsoleView();
            }}
          >
            <Icon name="menu" size={16} /> Console view
          </button>
          {onLock && <button type="button" className="dsk-menu-item" onClick={onLock}>Lock now</button>}
          <button type="button" className="dsk-menu-item dsk-menu-danger" onClick={onSignOut}>
            <Icon name="lock" size={16} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function DesktopShell(props: DesktopShellProps) {
  const { boxName, status, bell, nav, current, pinned = [], apps = [], now, timeZone, person, displayName, demo, onSearch, onConsoleView, onSignOut, onLock, children } = props;
  const { fleet, waiting, machines = [], commands = [], onRunCommand, onOpen, runBar = false, waitingRequests = [] } = props;
  const location = useLocation();
  const navigate = useNavigate();
  const atHome = current === 'home';
  const wm = useWindows();
  const managed = !!routeFor(location.pathname);
  // Home loads once the person has been on the desktop: a deep link opens just its window over the
  // wallpaper, and a phone (every window full screen) never pays for a Home nobody can see.
  const [desktopSeen, setDesktopSeen] = useState(atHome);
  if (atHome && !desktopSeen) setDesktopSeen(true);
  function closeWindow(id: string) {
    const frame = rootRef.current?.querySelector<HTMLElement>(`[data-window-id="${id}"]`);
    if (document.startViewTransition && frame && window.matchMedia?.('(prefers-reduced-motion: no-preference)').matches) {
      frame.style.viewTransitionName = 'wm-dismiss';
      document.startViewTransition(() => flushSync(() => wm.dismiss(id)));
    } else wm.dismiss(id);
  }
  const rootRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const [launchpad, setLaunchpad] = useState(false);
  const dockPreference = useOptionalCustomize()?.prefs.dockOrder;
  const { dock, more } = useMemo(() => dockSplit(nav, orderDock(dockOrder(), dockPreference)), [nav, dockPreference]);
  const openExtras = onWorkspace(wm.windows, wm.workspace).filter(w => !dock.some(item => item.id === w.id)).map(w => {
    const screen = routeFor(w.path)!.screen;
    return { id: w.id, label: screen.title, icon: screen.icon, href: w.path } as NavItem;
  });
  const moreBadge = more.reduce((s, n) => s + (n.badge ?? 0), 0);
  const runBarOn = runBar && !!onRunCommand;
  const runRef = useRef<HTMLInputElement>(null);

  // The window starts under the menu bar, which can wrap on phones: track its height.
  useEffect(() => {
    const bar = barRef.current;
    const root = rootRef.current;
    if (!bar || !root) return;
    return trackBarHeight(bar, root, '--dsk-bar-real');
  }, []);

  // Every shortcut is an entry of shell/keys/keymap.ts; the palette (Ctrl/⌘ K) is bound in Shell.
  const [sheet, setSheet] = useState(false);
  const busy = () => launchpad || sheet || overlayOpen();
  useKeymap({
    launchpad: () => setLaunchpad((o) => !o),
    'run-bar': () => (runBarOn && runRef.current ? runRef.current.focus() : false),
    close: () => (wm.active && !busy() ? closeWindow(wm.active) : false),
    shortcuts: () => (busy() ? false : setSheet(true)),
    'cycle-next': () => wm.cycle(1),
    'cycle-previous': () => wm.cycle(-1),
    tiling: () => (wm.narrow ? false : wm.toggleTiling()),
    ...Object.fromEntries(Array.from({ length: WORKSPACES }, (_, n) => [
      [`workspace-${n + 1}`, () => wm.switchWorkspace(n)],
      [`send-${n + 1}`, () => (wm.active ? wm.sendWindow(wm.active, n) : false)],
    ]).flat() as [string, () => void][]),
  });

  return (
    <div ref={rootRef} className={atHome ? 'dsk dsk-at-home' : 'dsk dsk-in-window'}>
      <a href="#om-main" className="om-skip">
        Skip to content
      </a>
      <header ref={barRef} className="dsk-bar">
        <a href="/" className="dsk-brand" aria-label={`${boxName}: desktop`}>
          <BrandMark size={22} />
          <span className="dsk-box">{boxName}</span>
        </a>
        <div className="dsk-status">
          {fleet && <FleetCountsView counts={fleet} />}
          {status}
          {demo && (
            <span className="dsk-demo" title="This screen shows sample data, not a real box">
              <span className="dsk-demo-short" aria-hidden="true">
                Demo
              </span>
              <span className="dsk-demo-long">Demo data</span>
            </span>
          )}
        </div>
        {waiting !== undefined && <NeedsYouChip waiting={waiting} />}
        <Clock now={now} timeZone={timeZone} />
        <div className="dsk-actions">
          <div className="wm-spaces" role="group" aria-label="Workspaces">
            {Array.from({ length: WORKSPACES }, (_, n) => (
              <button key={n} type="button" className="wm-space" aria-pressed={wm.workspace === n} data-busy={onWorkspace(wm.windows, n).length > 0 || undefined}
                aria-label={`Workspace ${n + 1}${onWorkspace(wm.windows, n).length ? ', has windows' : ''}`} title={`Workspace ${n + 1} (Alt ${n + 1})`} onClick={() => wm.switchWorkspace(n)}>
                {n + 1}
              </button>
            ))}
          </div>
          {!wm.narrow && (
            <button type="button" className="wm-tiling" aria-label={`Tiling: ${wm.tiling ? LAYOUT_LABELS[wm.tiling] : 'off'}, next layout`} title="Tiling: click for the next layout (Alt T turns it on or off)" onClick={() => wm.setTiling(nextLayout(wm.tiling))}>
              {wm.tiling ? LAYOUT_LABELS[wm.tiling] : 'Tiling off'}
            </button>
          )}
          <button type="button" className="dsk-iconbtn" onClick={onSearch} aria-label="Search (Ctrl K)" title="Search (Ctrl K)">
            <Icon name="search" size={18} />
          </button>
          {nav.some((n) => n.id === 'usage') && (
            <a href="/usage" className="dsk-iconbtn dsk-wide-only" aria-label="Live usage" title="Live usage" aria-current={current === 'usage' ? 'page' : undefined}>
              <Icon name="gauge" size={18} />
            </a>
          )}
          {bell}
          <PersonMenu person={person} displayName={displayName} demo={demo} onConsoleView={onConsoleView} onSignOut={onSignOut} onLock={onLock} usageHref={nav.some((n) => n.id === 'usage') ? '/usage' : undefined} />
        </div>
      </header>

      {/* The desktop (Home) stays painted under the windows, so a window opens over the wallpaper and the
          tile column instead of replacing them. While a window has focus the desktop is inert, and a click on
          the bare wallpaper comes back to it. One element in both cases, so Home never remounts. */}
      {atHome || managed ? (
        <div id={managed ? undefined : 'om-main'} role={managed ? undefined : 'main'} tabIndex={-1} className="dsk-desktop" inert={managed} aria-hidden={managed || undefined}>
          {(atHome || (desktopSeen && !wm.narrow)) && <ScreenRoutes location="/" />}
        </div>
      ) : <main id="om-main" tabIndex={-1} className="dsk-desktop">{children}</main>}
      <div id={managed ? 'om-main' : undefined} role={managed ? 'main' : undefined} tabIndex={-1} className="dsk-stage wm-stage" hidden={!atHome && !managed}
        onClick={(e) => { if (managed && e.target === e.currentTarget) navigate('/'); }}>
        {[...wm.windows].reverse().map((item, index) => <WindowFrame z={wm.windows.length - index} key={item.id} item={item} active={wm.active === item.id} narrow={wm.narrow} here={item.ws === wm.workspace} tile={wm.tiles[item.id]}
          onSend={n => wm.sendWindow(item.id, n)}
          onPosition={rect => wm.update(position(wm.windows, item.id, rect))}
          onMax={() => wm.update(toggleMax(wm.windows, item.id))}
          onMinimise={() => wm.dismiss(item.id, true)} onClose={() => closeWindow(item.id)} />)}
      </div>

      <nav className="dsk-dock" aria-label="Main">
        <button type="button" className="dsk-dock-item dsk-dock-launcher" aria-haspopup="dialog" aria-expanded={launchpad} onClick={() => setLaunchpad(true)} title="OneMind launcher: every screen, app and command (Ctrl /)">
          <span className="dsk-tile dsk-tile-mark" aria-hidden="true">
            <BrandMark size={30} />
          </span>
          <span className="dsk-dock-label">OneMind</span>
          <span className="om-visually-hidden">launcher: all screens and apps</span>
          {moreBadge > 0 && (
            <span className="dsk-badge">
              <span aria-hidden="true">{moreBadge}</span>
              <span className="om-visually-hidden">{`${moreBadge} new in other screens`}</span>
            </span>
          )}
        </button>
        <span className="dsk-dock-sep" aria-hidden="true" />
        <ul className="dsk-dock-group">
          {[...dock, ...openExtras].map((item) => (
            <li key={item.id}>
              <a href={wm.windows.find(w => w.id === item.id && w.minimised)?.path ?? item.href} className="dsk-dock-item" data-open={wm.windows.some(w => w.id === item.id) || undefined} aria-current={item.id === current ? 'page' : undefined}>
                <ScreenTile id={item.id} icon={item.icon} />
                <span className="dsk-dock-label">{item.label}</span>
                <Badge item={item} />
              </a>
            </li>
          ))}
        </ul>
        <DockApps apps={pinned} runBar={runBarOn} onMore={() => setLaunchpad(true)} />
        {runBarOn && (
          <>
            <span className="dsk-dock-sep" aria-hidden="true" />
            <RunBar ref={runRef} commands={commands} waiting={waitingRequests} onRun={onRunCommand!} onOpen={(href) => onOpen?.(href)} />
          </>
        )}
      </nav>

      {launchpad && <Launchpad nav={nav} apps={apps} machines={machines} commands={commands} onRun={onRunCommand} onClose={() => setLaunchpad(false)} onShortcuts={() => { setLaunchpad(false); setSheet(true); }} />}
      <ShortcutSheet open={sheet} onClose={() => setSheet(false)} />
    </div>
  );
}

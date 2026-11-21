// SPDX-License-Identifier: Apache-2.0
// The desktop frame (D-016): no sidebar. "/" is the wallpaper desktop (Home); every other screen
// opens as a window over the wallpaper, with a back button for nested pages, a close button and
// Esc back to the desktop. A slim menu bar carries the OneMind mark, the hub clock and state,
// search, the bell and the person menu. The dock holds the everyday screens and pinned apps;
// Launchpad (the grid button, or Ctrl/⌘ + /) shows every screen and app with a search field.
// Pattern studied in umbrelOS 2.0.1 (PolyForm NC: no code, asset or text copied;
// docs/learning/umbrelos-2-teardown.md). OneMind's own look: brand mark, signature wallpaper,
// one colour per screen, approvals first.
// Links are plain anchors: Shell's click handler routes them without a page reload.
import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { AppIcon, BrandMark, Icon, type NavItem } from '@onemind/ui';
import './desktop.css';

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
  /** Installed apps, listed in Launchpad. */
  apps?: DockApp[];
  /** Hub clock (ms) and time zone, for the menu-bar clock. */
  now: number;
  timeZone: string;
  person?: DesktopPerson;
  demo?: boolean;
  onSearch: () => void;
  onConsoleView: () => void;
  onSignOut: () => void;
  children: ReactNode;
}

/** Screens that stay in the dock; everything else is one click away in Launchpad. */
export const DOCK_IDS = ['home', 'market', 'installed', 'approvals', 'activity', 'settings'] as const;

/** One colour per screen, so a place is recognised before its name is read. White glyph on each. */
export const SCREEN_HUES: Record<string, readonly [string, string]> = {
  home: ['#ff4d55', '#b3101c'],
  market: ['#6d84ff', '#3340c4'],
  installed: ['#34c77b', '#147a45'],
  approvals: ['#f59e0b', '#b45309'],
  activity: ['#22c5b0', '#0b7a6c'],
  settings: ['#8f99a6', '#3e4652'],
  nodes: ['#38a8f0', '#0b5f9a'],
  machines: ['#9b7bf7', '#5b2bc8'],
  alerts: ['#f4637c', '#b0123a'],
  storage: ['#f6a35c', '#b8460c'],
  backups: ['#3fc6db', '#0c6b80'],
  network: ['#4aa8e0', '#1d5f99'],
  coming: ['#7d8794', '#3a414b'],
  'control-hub': ['#e5484d', '#7c0d16'],
  agents: ['#d96cf0', '#8a1fa3'],
};
const FALLBACK_HUE = ['#7d8794', '#3a414b'] as const;

export function tileStyle(id: string): CSSProperties {
  const [a, b] = SCREEN_HUES[id] ?? FALLBACK_HUE;
  return { '--dsk-tile-a': a, '--dsk-tile-b': b } as CSSProperties;
}

/** Split the nav into dock items (fixed order) and Launchpad-only items (nav order). */
export function dockSplit(nav: NavItem[]): { dock: NavItem[]; more: NavItem[] } {
  const dock = DOCK_IDS.flatMap((id) => nav.filter((n) => n.id === id));
  const more = nav.filter((n) => !(DOCK_IDS as readonly string[]).includes(n.id));
  return { dock, more };
}

/** A path one level up inside the same screen ("/market/x" → "/market"), or null at the top. */
export function parentPath(pathname: string): string | null {
  const parts = pathname.split('/').filter(Boolean);
  return parts.length > 1 ? `/${parts.slice(0, -1).join('/')}` : null;
}

/**
 * Esc belongs to something else: a modal dialog or the palette, or a popover opened from the
 * menu bar (the bell, the account menu: their triggers say aria-expanded). Expandable sections
 * inside a page do not count.
 */
function overlayOpen(except?: Element | null): boolean {
  return [...document.querySelectorAll('[aria-modal="true"], dialog[open], .dsk-bar [aria-expanded="true"]')].some((e) => e !== except);
}
function typingIn(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
}

function ScreenTile({ id, icon, size = 44 }: { id: string; icon: NavItem['icon']; size?: number }) {
  return (
    <span className="dsk-tile" style={{ ...tileStyle(id), width: size, height: size }} aria-hidden="true">
      <Icon name={icon} size={Math.round(size * 0.48)} />
    </span>
  );
}

function Badge({ item }: { item: NavItem }) {
  if (!item.badge) return null;
  return (
    <span className="dsk-badge">
      <span aria-hidden="true">{item.badge}</span>
      <span className="om-visually-hidden">{item.badgeLabel ?? `${item.badge} new`}</span>
    </span>
  );
}

function GridGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      {[5, 12, 19].flatMap((y) => [5, 12, 19].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2" fill="currentColor" />))}
    </svg>
  );
}

function Clock({ now, timeZone }: { now: number; timeZone: string }) {
  const d = new Date(now);
  const day = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric', timeZone }).format(d);
  const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZone }).format(d);
  return (
    <time className="dsk-clock" dateTime={d.toISOString()} title="Hub time">
      <span className="dsk-clock-day">{day}</span> {time}
    </time>
  );
}

function PersonMenu({ person, demo, onConsoleView, onSignOut }: Pick<DesktopShellProps, 'person' | 'demo' | 'onConsoleView' | 'onSignOut'>) {
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
  const initial = (person?.id ?? '?').slice(0, 1).toUpperCase();
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
          <button type="button" className="dsk-menu-item dsk-menu-danger" onClick={onSignOut}>
            <Icon name="lock" size={16} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Launchpad({ nav, apps, onClose }: { nav: NavItem[]; apps: DockApp[]; onClose: () => void }) {
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const title = useId();
  const input = useRef<HTMLInputElement>(null);
  // The latest onClose without re-running the effect: the shell re-renders on every hub poll,
  // and re-running would pull focus back to the search field each time.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !overlayOpen(ref.current)) {
        e.preventDefault();
        closeRef.current();
        return;
      }
      // Keep Tab inside Launchpad while it is open (aria-modal).
      if (e.key === 'Tab' && ref.current) {
        const items = [...ref.current.querySelectorAll<HTMLElement>('a[href], button, input, [tabindex]:not([tabindex="-1"])')];
        const first = items[0];
        const last = items[items.length - 1];
        if (!first || !last) return;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      // Back to whatever opened it (the dock's All button), if it is still on the page.
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  const needle = q.trim().toLowerCase();
  const screens = nav.filter((n) => !needle || n.label.toLowerCase().includes(needle));
  const shownApps = apps.filter((a) => !needle || a.name.toLowerCase().includes(needle));
  return (
    <div className="dsk-launchpad" role="dialog" aria-modal="true" aria-labelledby={title} ref={ref} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dsk-launchpad-inner">
        <h2 id={title} className="om-visually-hidden">
          Launchpad
        </h2>
        <label className="dsk-launchpad-search">
          <Icon name="search" size={18} />
          <span className="om-visually-hidden">Find a screen or app</span>
          <input ref={input} type="search" placeholder="Find a screen or app" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <section aria-label="Screens">
          <h3 className="dsk-launchpad-head">Screens</h3>
          <ul className="dsk-launchpad-grid">
            {screens.map((n) => (
              <li key={n.id}>
                <a href={n.href} className="dsk-launchpad-item" onClick={onClose}>
                  <ScreenTile id={n.id} icon={n.icon} size={64} />
                  <span className="dsk-launchpad-label">{n.label}</span>
                  <Badge item={n} />
                </a>
              </li>
            ))}
          </ul>
        </section>
        {shownApps.length > 0 && (
          <section aria-label="Your apps">
            <h3 className="dsk-launchpad-head">Your apps</h3>
            <ul className="dsk-launchpad-grid">
              {shownApps.map((a) => (
                <li key={a.id}>
                  <a href={a.href} className="dsk-launchpad-item" onClick={onClose}>
                    <AppIcon app={a} size={64} />
                    <span className="dsk-launchpad-label">{a.name}</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}
        {screens.length === 0 && shownApps.length === 0 && <p className="dsk-launchpad-none">Nothing matches “{q}”. Try the search (Ctrl K) for settings and actions.</p>}
      </div>
    </div>
  );
}

export function DesktopShell(props: DesktopShellProps) {
  const { boxName, status, bell, nav, current, pinned = [], apps = [], now, timeZone, person, demo, onSearch, onConsoleView, onSignOut, children } = props;
  const navigate = useNavigate();
  const location = useLocation();
  const atHome = current === 'home';
  const here = nav.find((n) => n.id === current);
  const title = here?.label ?? boxName;
  const up = parentPath(location.pathname);
  const windowLabel = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const [launchpad, setLaunchpad] = useState(false);
  const { dock, more } = useMemo(() => dockSplit(nav), [nav]);
  const moreBadge = more.reduce((s, n) => s + (n.badge ?? 0), 0);

  // The window starts under the menu bar, which can wrap on phones: track its height.
  useEffect(() => {
    const bar = barRef.current;
    const root = rootRef.current;
    if (!bar || !root || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => root.style.setProperty('--dsk-bar-real', `${bar.offsetHeight}px`));
    ro.observe(bar);
    return () => ro.disconnect();
  }, []);

  // Esc closes the window (back to the desktop); Ctrl/⌘ + / opens Launchpad.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        setLaunchpad((o) => !o);
        return;
      }
      if (e.key === 'Escape' && !atHome && !launchpad && !overlayOpen() && !typingIn(e.target)) navigate('/');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [atHome, launchpad, navigate]);

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
        <div className="dsk-status">{status}</div>
        <Clock now={now} timeZone={timeZone} />
        <div className="dsk-actions">
          <button type="button" className="dsk-iconbtn" onClick={onSearch} aria-label="Search (Ctrl K)" title="Search (Ctrl K)">
            <Icon name="search" size={18} />
          </button>
          {bell}
          <PersonMenu person={person} demo={demo} onConsoleView={onConsoleView} onSignOut={onSignOut} />
        </div>
      </header>

      {atHome ? (
        <main id="om-main" tabIndex={-1} className="dsk-desktop">
          {children}
        </main>
      ) : (
        <div className="dsk-stage">
          <div className="dsk-scrim" aria-hidden="true" onClick={() => navigate('/')} />
          <section className="dsk-window" aria-labelledby={windowLabel} key={current}>
            <div className="dsk-window-bar">
              {up ? (
                <a href={up} className="dsk-wbtn" aria-label="Back" title="Back">
                  <Icon name="chevron" size={16} className="dsk-flip" />
                </a>
              ) : (
                here && <ScreenTile id={here.id} icon={here.icon} size={26} />
              )}
              <span id={windowLabel} className="dsk-window-title">
                {title}
              </span>
              <a href="/" className="dsk-wbtn dsk-close" aria-label={`Close ${title}`} title="Close (Esc)">
                <Icon name="x" size={16} />
              </a>
            </div>
            {/* tabIndex 0: the window scrolls, so keyboard users must be able to reach it (axe scrollable-region-focusable). */}
            <main id="om-main" tabIndex={0} className="dsk-window-body">
              {children}
            </main>
          </section>
        </div>
      )}

      <nav className="dsk-dock" aria-label="Main">
        <ul className="dsk-dock-group">
          {dock.map((item) => (
            <li key={item.id}>
              <a href={item.href} className="dsk-dock-item" aria-current={item.id === current ? 'page' : undefined}>
                <ScreenTile id={item.id} icon={item.icon} />
                <span className="dsk-dock-label">{item.label}</span>
                <Badge item={item} />
              </a>
            </li>
          ))}
        </ul>
        {pinned.length > 0 && (
          <>
            <span className="dsk-dock-sep" aria-hidden="true" />
            <ul className="dsk-dock-group" aria-label="Pinned apps">
              {pinned.map((a) => (
                <li key={a.id}>
                  <a href={a.href} className="dsk-dock-item dsk-dock-app">
                    <AppIcon app={a} size={44} />
                    <span className="dsk-dock-label">{a.name}</span>
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
        <span className="dsk-dock-sep" aria-hidden="true" />
        <button type="button" className="dsk-dock-item" aria-haspopup="dialog" aria-expanded={launchpad} onClick={() => setLaunchpad(true)} title="All screens and apps (Ctrl /)">
          <span className="dsk-tile dsk-tile-launch" aria-hidden="true">
            <GridGlyph />
          </span>
          <span className="dsk-dock-label">All</span>
          <span className="om-visually-hidden">screens and apps</span>
          {moreBadge > 0 && (
            <span className="dsk-badge">
              <span aria-hidden="true">{moreBadge}</span>
              <span className="om-visually-hidden">{`${moreBadge} new in other screens`}</span>
            </span>
          )}
        </button>
      </nav>

      {launchpad && <Launchpad nav={nav} apps={apps} onClose={() => setLaunchpad(false)} />}
    </div>
  );
}

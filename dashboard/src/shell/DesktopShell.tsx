// SPDX-License-Identifier: Apache-2.0
// The desktop frame (D-016): no sidebar. "/" is the wallpaper desktop (Home); every other screen
// opens as a window over the wallpaper, with a close button and Esc back to the desktop. A dock
// at the bottom is the main navigation (the same items and badges as the Console sidebar) plus
// the apps the person pinned on Home. Pattern studied in umbrelOS 2.0.1 (PolyForm NC: no code,
// asset or text copied; docs/learning/umbrelos-2-teardown.md).
// Links are plain anchors: Shell's click handler routes them without a page reload.
import { Fragment, useEffect, useId, useRef, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { AppIcon, Icon, type NavItem } from '@onemind/ui';
import './desktop.css';

export interface DockApp {
  id: string;
  name: string;
  icon?: string | null;
  href: string;
}

export interface DesktopShellProps {
  boxName: string;
  status?: ReactNode;
  account?: ReactNode;
  nav: NavItem[];
  /** Nav id of the current route ('home' = the desktop). */
  current: string;
  /** Apps pinned on Home, shown after the navigation in the dock. */
  pinned?: DockApp[];
  children: ReactNode;
}

/** Nav ids shown first in the dock; the rest follow in their sidebar groups. */
const GROUP_ORDER = ['', 'Your box', 'System'];

export function dockGroups(nav: NavItem[]): NavItem[][] {
  const primary = nav.filter((n) => n.primary);
  const rest = nav.filter((n) => !n.primary);
  const groups = Array.from(new Set(rest.map((n) => n.group ?? ''))).sort((a, b) => GROUP_ORDER.indexOf(a) - GROUP_ORDER.indexOf(b));
  return [primary, ...groups.map((g) => rest.filter((n) => (n.group ?? '') === g))].filter((g) => g.length > 0);
}

/** A modal dialog or the command palette is open: Esc belongs to it, not to the window. */
function overlayOpen(): boolean {
  return document.querySelector('[aria-modal="true"], dialog[open]') !== null;
}

export function DesktopShell({ boxName, status, account, nav, current, pinned = [], children }: DesktopShellProps) {
  const navigate = useNavigate();
  const atHome = current === 'home';
  const title = nav.find((n) => n.id === current)?.label ?? boxName;
  const windowLabel = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLElement>(null);

  // The window starts under the top bar, which wraps to two lines on phones: track its height.
  useEffect(() => {
    const bar = barRef.current;
    const root = rootRef.current;
    if (!bar || !root || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => root.style.setProperty('--dsk-bar-real', `${bar.offsetHeight}px`));
    ro.observe(bar);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (atHome) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented || overlayOpen()) return;
      navigate('/');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [atHome, navigate]);

  const groups = dockGroups(nav);

  return (
    <div ref={rootRef} className={atHome ? 'dsk dsk-at-home' : 'dsk dsk-in-window'}>
      <a href="#om-main" className="om-skip">
        Skip to content
      </a>
      <header ref={barRef} className="dsk-bar">
        <span className="dsk-box">{boxName}</span>
        <div className="dsk-status">{status}</div>
        <div className="dsk-account">{account}</div>
      </header>

      {atHome ? (
        <main id="om-main" tabIndex={-1} className="dsk-desktop">
          {children}
        </main>
      ) : (
        <div className="dsk-stage">
          <div className="dsk-scrim" aria-hidden="true" onClick={() => navigate('/')} />
          <section className="dsk-window" aria-labelledby={windowLabel}>
            <div className="dsk-window-bar">
              <span id={windowLabel} className="dsk-window-title">
                {title}
              </span>
              <a href="/" className="dsk-close" aria-label={`Close ${title}`} title="Close (Esc)">
                <Icon name="x" size={16} />
              </a>
            </div>
            <main id="om-main" tabIndex={-1} className="dsk-window-body">
              {children}
            </main>
          </section>
        </div>
      )}

      <nav className="dsk-dock" aria-label="Main">
        {groups.map((items, gi) => (
          <Fragment key={gi}>
            {gi > 0 && <span className="dsk-dock-sep" aria-hidden="true" />}
            <ul className="dsk-dock-group">
              {items.map((item) => (
                <li key={item.id}>
                  <a href={item.href} className="dsk-dock-item" aria-current={item.id === current ? 'page' : undefined}>
                    <span className="dsk-dock-icon">
                      <Icon name={item.icon} size={22} />
                    </span>
                    <span className="dsk-dock-label">{item.label}</span>
                    {item.badge ? (
                      <span className="dsk-dock-badge">
                        <span aria-hidden="true">{item.badge}</span>
                        <span className="om-visually-hidden">{item.badgeLabel ?? `${item.badge} new`}</span>
                      </span>
                    ) : null}
                  </a>
                </li>
              ))}
            </ul>
          </Fragment>
        ))}
        {pinned.length > 0 && (
          <>
            <span className="dsk-dock-sep" aria-hidden="true" />
            <ul className="dsk-dock-group" aria-label="Pinned apps">
              {pinned.map((a) => (
                <li key={a.id}>
                  <a href={a.href} className="dsk-dock-item dsk-dock-app">
                    <AppIcon app={a} size={40} />
                    <span className="dsk-dock-label">{a.name}</span>
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>
    </div>
  );
}

// SPDX-License-Identifier: Apache-2.0
// The dashboard frame (docs/design/IA.md §1): a sidebar on wide screens, a bottom tab bar
// with a "More" sheet on phones, a top bar with the box name and connection state, and a
// skip link. Router-agnostic: items are plain links; pass onNavigate to intercept clicks.
import { useState, type MouseEvent, type ReactNode } from 'react';
import { cx } from '../lib/cx';
import { BrandMark, BRAND } from './BrandMark';
import { Icon, type IconName } from './Icon';

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: IconName;
  /** Count shown as a badge, e.g. pending approvals. 0 or undefined hides it. */
  badge?: number;
  /** Words for the badge, e.g. "3 waiting". */
  badgeLabel?: string;
  /** Shown in the phone tab bar (at most 4); the rest go under "More". */
  primary?: boolean;
  /** Group heading in the sidebar. */
  group?: string;
}

export interface AppShellProps {
  boxName: string;
  /** Top bar status, e.g. a FreshnessPill for the hub connection. */
  status?: ReactNode;
  /** Right side of the top bar: person menu, theme switch. */
  account?: ReactNode;
  nav: NavItem[];
  current: string;
  onNavigate?: (id: string, e: MouseEvent<HTMLAnchorElement>) => void;
  children: ReactNode;
}

function Badge({ item }: { item: NavItem }) {
  if (!item.badge) return null;
  return (
    <span className="om-nav-badge">
      <span aria-hidden="true">{item.badge}</span>
      <span className="om-visually-hidden">{item.badgeLabel ?? `${item.badge} new`}</span>
    </span>
  );
}

export function AppShell({ boxName, status, account, nav, current, onNavigate, children }: AppShellProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const primary = nav.filter((n) => n.primary).slice(0, 4);
  const rest = nav.filter((n) => !primary.includes(n));
  const moreBadge = rest.reduce((s, n) => s + (n.badge ?? 0), 0);
  const groups = Array.from(new Set(nav.map((n) => n.group ?? '')));

  const link = (item: NavItem, cls: string, compact = false) => (
    <a
      href={item.href}
      className={cls}
      aria-current={item.id === current ? 'page' : undefined}
      onClick={(e) => {
        setMoreOpen(false);
        onNavigate?.(item.id, e);
      }}
    >
      <Icon name={item.icon} size={compact ? 22 : 20} />
      <span className="om-nav-label">{item.label}</span>
      <Badge item={item} />
    </a>
  );

  return (
    <div className="om-shell">
      <a href="#om-main" className="om-skip">
        Skip to content
      </a>
      <aside className="om-sidebar">
        <div className="om-brand">
          <BrandMark className="om-brand-mark" />
          <span className="om-brand-text">
            <span className="om-brand-name">{BRAND.shortName}</span>
            <span className="om-brand-box">{boxName}</span>
          </span>
        </div>
        <nav aria-label="Main" className="om-sidenav">
          {groups.map((g) => (
            <div key={g || 'main'} className="om-nav-group">
              {g && <p className="om-nav-group-title">{g}</p>}
              <ul>
                {nav
                  .filter((n) => (n.group ?? '') === g)
                  .map((n) => (
                    <li key={n.id}>{link(n, 'om-nav-link')}</li>
                  ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      <div className="om-frame">
        <header className="om-topbar">
          <span className="om-topbar-box">{boxName}</span>
          <div className="om-topbar-status">{status}</div>
          <div className="om-topbar-account">{account}</div>
        </header>
        <main id="om-main" tabIndex={-1} className="om-main">
          {children}
        </main>
      </div>
      <nav aria-label="Main (compact)" className="om-tabbar">
        <ul>
          {primary.map((n) => (
            <li key={n.id}>{link(n, 'om-tab', true)}</li>
          ))}
          <li>
            <button
              type="button"
              className={cx('om-tab', rest.some((n) => n.id === current) && 'om-tab-on')}
              aria-expanded={moreOpen}
              aria-controls="om-more"
              onClick={() => setMoreOpen((v) => !v)}
            >
              <Icon name="menu" size={22} />
              <span className="om-nav-label">More</span>
              {moreBadge > 0 && (
                <span className="om-nav-badge">
                  <span aria-hidden="true">{moreBadge}</span>
                  <span className="om-visually-hidden">{moreBadge} new</span>
                </span>
              )}
            </button>
          </li>
        </ul>
        <ul id="om-more" className="om-more" hidden={!moreOpen}>
          {rest.map((n) => (
            <li key={n.id}>{link(n, 'om-nav-link')}</li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

/** Page header inside <main>: one h1, optional lede and actions. */
export function PageHeader({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="om-page-head">
      <div>
        <h1 className="om-page-title">{title}</h1>
        {lede && <p className="om-page-lede">{lede}</p>}
      </div>
      {actions && <div className="om-page-actions">{actions}</div>}
    </div>
  );
}

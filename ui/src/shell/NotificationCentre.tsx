// SPDX-License-Identifier: Apache-2.0
// Notification centre: a bell in the top bar opens a panel (a bottom sheet on phones) with
// filters, day groups, mark read/unread, mark all read, and a deep link per notification.
// It is a window onto the alert record (NOT-P1); toasts never carry the only copy.
import { useEffect, useId, useRef, useState } from 'react';
import { cx } from '../lib/cx';
import { formatAgo, secondsSince } from '../lib/time';
import { StatusPill } from '../components/StatusPill';
import { ShellIcon } from './icons';
import { filterNotifications, groupByDay, KIND_META, needsYou, safeDeepLink, unreadCount, type NotificationFilter, type ShellNotification } from './notifications';
import { StateView } from './StateView';
import type { GatewayError, ViewState } from './states';
import './shell.css';

const FILTERS: Array<[NotificationFilter, string]> = [
  ['all', 'All'],
  ['unread', 'Unread'],
  ['needs-you', 'Needs you'],
];

export interface NotificationCentreProps {
  items: ShellNotification[];
  now: number;
  state?: ViewState;
  ageSeconds?: number;
  error?: GatewayError;
  onRetry?: () => void;
  onOpen?: (n: ShellNotification) => void;
  onSetRead: (ids: string[], read: boolean) => void;
  onReadAll: () => void;
  initialFilter?: NotificationFilter;
  /** Link to the full alert centre page. */
  allHref?: string;
  settingsHref?: string;
  /** Heading level; 2 inside a popover. */
  headingId?: string;
}

/** The panel content; place it in NotificationBell's popover or on a page. */
export function NotificationCentre({
  items,
  now,
  state = 'ready',
  ageSeconds,
  error,
  onRetry,
  onOpen,
  onSetRead,
  onReadAll,
  initialFilter = 'all',
  allHref = '#/notifications',
  settingsHref = '#/settings/notifications',
  headingId,
}: NotificationCentreProps) {
  const [filter, setFilter] = useState<NotificationFilter>(initialFilter);
  const fallbackId = useId();
  const hid = headingId ?? fallbackId;
  const unread = unreadCount(items);
  const shown = filterNotifications(items, filter);
  const counts: Record<NotificationFilter, number> = { all: items.length, unread, 'needs-you': items.filter(needsYou).length };
  const writable = state === 'ready' || state === 'empty';

  return (
    <section className="oms-nc" aria-labelledby={hid}>
      <header className="oms-nc-head">
        <div>
          <h2 id={hid} className="oms-nc-title">
            Notifications
          </h2>
          <p className="oms-nc-sub">{unread === 0 ? 'Nothing unread' : `${unread} unread`}</p>
        </div>
        <button type="button" className="om-btn om-btn-ghost om-btn-sm" onClick={onReadAll} disabled={unread === 0 || !writable} title={!writable ? 'Available when the hub answers' : undefined}>
          <ShellIcon name="check" size={16} />
          Mark all read
        </button>
      </header>
      <div className="oms-tabs" role="radiogroup" aria-label="Show">
        {FILTERS.map(([f, label]) => (
          <button key={f} type="button" role="radio" aria-checked={filter === f} className="oms-tab-btn" onClick={() => setFilter(f)}>
            {label}
            {counts[f] > 0 && <span className={cx('oms-count', f === 'needs-you' && 'oms-count-warn')}>{counts[f]}</span>}
          </button>
        ))}
      </div>
      <div className="oms-nc-body">
        {state === 'loading' || state === 'error' || state === 'forbidden' ? (
          <StateView state={state} compact what="Loading notifications" error={error} onRetry={onRetry} forbiddenReason="Notifications are per person. Sign in to see yours." />
        ) : shown.length === 0 ? (
          <StateView state="empty" compact empty={filter === 'all' ? 'notifications' : filter === 'unread' ? 'notifications-unread' : 'notifications-needs-you'} />
        ) : (
          <StateView state={state === 'empty' ? 'ready' : state} ageSeconds={ageSeconds} onRetry={onRetry}>
            {groupByDay(shown, now).map((g) => (
              <div key={g.label} className="oms-nc-day">
                <h3 className="oms-nc-day-title">{g.label}</h3>
                <ul className="oms-nc-list">
                  {g.items.map((n) => {
                    const meta = KIND_META[n.kind];
                    return (
                      <li key={n.id} className={cx('oms-nc-item', !n.read && 'oms-nc-unread', `om-tone-${meta.tone}`)}>
                        <a
                          className="oms-nc-link"
                          href={safeDeepLink(n.href)}
                          onClick={() => {
                            if (!n.read && writable) onSetRead([n.id], true);
                            onOpen?.(n);
                          }}
                        >
                          <span className="oms-nc-icon">
                            <ShellIcon name={meta.icon} size={18} />
                          </span>
                          <span className="oms-nc-text">
                            <span className="oms-nc-item-title">
                              {!n.read && <span className="om-visually-hidden">Unread: </span>}
                              {n.title}
                            </span>
                            {n.body && <span className="oms-nc-item-body">{n.body}</span>}
                            <span className="oms-nc-meta">
                              <StatusPill tone={meta.tone} label={meta.label} dot={false} />
                              <span>
                                {n.source} · {formatAgo(secondsSince(n.created, now))}
                              </span>
                              <span className="oms-nc-go">
                                {n.linkLabel ?? meta.link}
                                <ShellIcon name="chevron" size={14} />
                              </span>
                            </span>
                          </span>
                        </a>
                        <button
                          type="button"
                          className="om-icon-btn oms-nc-toggle"
                          aria-label={n.read ? `Mark as unread: ${n.title}` : `Mark as read: ${n.title}`}
                          title={n.read ? 'Mark as unread' : 'Mark as read'}
                          disabled={!writable}
                          onClick={() => onSetRead([n.id], !n.read)}
                        >
                          <span className={cx('oms-dot', !n.read && 'oms-dot-on')} aria-hidden="true" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </StateView>
        )}
      </div>
      <footer className="oms-nc-foot">
        <a href={allHref}>Open alert centre</a>
        <a href={settingsHref}>Where notifications go</a>
      </footer>
    </section>
  );
}

export interface NotificationBellProps extends NotificationCentreProps {
  /** Start open (screenshots, deep links). */
  defaultOpen?: boolean;
}

/** Top-bar bell with an unread badge; opens the centre as a popover (sheet on phones). */
export function NotificationBell({ defaultOpen = false, ...centre }: NotificationBellProps) {
  const [open, setOpen] = useState(defaultOpen);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const popId = useId();
  const unread = unreadCount(centre.items);
  const urgent = centre.items.some(needsYou);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        btn.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!pop.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  useEffect(() => {
    if (open && !defaultOpen) pop.current?.querySelector<HTMLElement>('button, a')?.focus();
  }, [open, defaultOpen]);

  return (
    <div className="oms-bell-wrap">
      <button
        ref={btn}
        type="button"
        className={cx('oms-bell', open && 'oms-bell-open')}
        aria-expanded={open}
        aria-controls={popId}
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        onClick={() => setOpen((v) => !v)}
      >
        <ShellIcon name="bell" size={20} />
        {unread > 0 && (
          <span className={cx('oms-bell-badge', urgent && 'oms-bell-badge-urgent')} aria-hidden="true">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      <div ref={pop} id={popId} className="oms-pop" hidden={!open}>
        {open && <NotificationCentre {...centre} />}
      </div>
    </div>
  );
}

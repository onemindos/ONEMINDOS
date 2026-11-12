// SPDX-License-Identifier: Apache-2.0
// Notification centre logic. The record follows backlog NOT-P1
// ({id, severity, source, audience, title, body, fixable, fix_action, created, acked_by, resolved}),
// PROPOSED in docs/design/IA.md §2.9, plus `kind`, `read` and a deep link for the shell.
import type { Tone } from '../tokens/tokens';
import { formatDay } from '../lib/time';
import type { ShellIconName } from './icons';

export type NotificationKind =
  | 'approval_waiting'
  | 'update_applied'
  | 'backup_failed'
  | 'node_offline'
  | 'app_rolled_back'
  | 'app_installed'
  | 'info';

export type NotificationSeverity = 'critical' | 'warning' | 'info';

export interface ShellNotification {
  id: string;
  kind: NotificationKind;
  severity: NotificationSeverity;
  /** Which part of the system raised it: approvals, updates, backup, fabric, market. */
  source: string;
  title: string;
  body?: string;
  created: string;
  read: boolean;
  /** Deep link inside the dashboard, e.g. "#/approvals/a-7f31". */
  href: string;
  /** Words for the link, e.g. "Review request". */
  linkLabel?: string;
  /** The pending action, when this notification is about one (NOT-B3). */
  actionId?: string;
}

export const KIND_META: Record<NotificationKind, { icon: ShellIconName; tone: Tone; label: string; link: string }> = {
  approval_waiting: { icon: 'approvals', tone: 'warn', label: 'Approval waiting', link: 'Review request' },
  update_applied: { icon: 'updates', tone: 'ok', label: 'Update applied', link: 'See what changed' },
  backup_failed: { icon: 'backups', tone: 'bad', label: 'Backup failed', link: 'Open backups' },
  node_offline: { icon: 'offline', tone: 'neutral', label: 'Node offline', link: 'Open node' },
  app_rolled_back: { icon: 'undo', tone: 'bad', label: 'Rolled back', link: 'See why' },
  app_installed: { icon: 'check', tone: 'ok', label: 'Installed', link: 'Open app' },
  info: { icon: 'info', tone: 'info', label: 'Info', link: 'Open' },
};

export type NotificationFilter = 'all' | 'unread' | 'needs-you';

/** Needs a person: a request waiting, or anything critical that is not yet read. */
export function needsYou(n: ShellNotification): boolean {
  return (n.kind === 'approval_waiting' && !n.read) || (n.severity === 'critical' && !n.read);
}

export function unreadCount(list: ShellNotification[]): number {
  return list.filter((n) => !n.read).length;
}

export function filterNotifications(list: ShellNotification[], f: NotificationFilter): ShellNotification[] {
  if (f === 'unread') return list.filter((n) => !n.read);
  if (f === 'needs-you') return list.filter(needsYou);
  return list;
}

export interface DayGroup {
  label: string;
  items: ShellNotification[];
}

/** Newest first, grouped "Today", "Yesterday", then the date (UTC, the hub's day). */
export function groupByDay(list: ShellNotification[], now: number): DayGroup[] {
  const day = (t: number) => Math.floor(t / 86_400_000);
  const today = day(now);
  const sorted = [...list].sort((a, b) => Date.parse(b.created) - Date.parse(a.created));
  const groups: DayGroup[] = [];
  for (const n of sorted) {
    const d = day(Date.parse(n.created));
    const label = d === today ? 'Today' : d === today - 1 ? 'Yesterday' : formatDay(n.created);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(n);
    else groups.push({ label, items: [n] });
  }
  return groups;
}

export function setRead(list: ShellNotification[], ids: string[], read = true): ShellNotification[] {
  const s = new Set(ids);
  return list.map((n) => (s.has(n.id) && n.read !== read ? { ...n, read } : n));
}

export function markAllRead(list: ShellNotification[]): ShellNotification[] {
  return list.map((n) => (n.read ? n : { ...n, read: true }));
}

/** Only in-app links ("#/…" or "/…", not "//host") are followed; anything else falls back to the alert centre. */
export function safeDeepLink(href: string): string {
  if (/^#\/[\w\-./%?=&]*$/.test(href)) return href;
  if (/^\/(?!\/)[\w\-./%?=&#]*$/.test(href)) return href;
  return '#/notifications';
}

/** API calls behind each control (P4); the endpoints are PROPOSED (NOT-P1). */
export const NOTIFICATION_API = {
  list: 'GET /v1/notifications',
  read: (id: string) => `POST /v1/notifications/${id}/read`,
  unread: (id: string) => `POST /v1/notifications/${id}/unread`,
  readAll: 'POST /v1/notifications/read-all',
} as const;

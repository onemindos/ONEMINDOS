// SPDX-License-Identifier: Apache-2.0
// One notification centre (UI sprint P1): the hub's own notifications (GET /v1/notifications)
// come first, then open alerts (GET /v1/alerts) that have no notification yet, then the facts
// the browser can derive from actions and nodes (adapters.notificationsFrom). A fact the hub
// already reports is never listed twice. Text from the hub is data: the bell renders it as text.
import type { ShellNotification } from '@onemind/ui';
import type { AlertInfo, NotificationItem } from '../api/wiring';
import { href } from '../shell/routes';

/** Ids carry their origin so a click knows whether to tell the hub or only this browser. */
export const SERVER_PREFIX = 'ntf:';
export const ALERT_PREFIX = 'alr:';
export const isServerId = (id: string) => id.startsWith(SERVER_PREFIX);

function kindFor(topic: string, severity: ShellNotification['severity'], actionId: string | null): ShellNotification['kind'] {
  if (topic === 'approvals' && actionId) return 'approval_waiting';
  if (topic === 'backups' && severity !== 'info') return 'backup_failed';
  if (topic === 'updates') return 'update_applied';
  if (topic === 'nodes' || topic === 'fabric') return 'node_offline';
  return 'info';
}

function topicHref(topic: string, actionId: string | null): string {
  if (actionId) return href.approval(actionId);
  switch (topic) {
    case 'approvals': return href.approvals;
    case 'backups': return href.setting('backups');
    case 'updates': return href.setting('updates');
    case 'nodes':
    case 'fabric': return href.nodes;
    case 'alerts':
    case 'storage':
    case 'monitoring': return href.alerts;
    default: return href.setting('notifications');
  }
}

export function fromServer(items: readonly NotificationItem[]): ShellNotification[] {
  return items.map((n) => ({
    id: SERVER_PREFIX + n.id,
    kind: kindFor(n.topic, n.severity, n.action_id),
    severity: n.severity,
    source: n.topic,
    title: n.title,
    body: n.body || undefined,
    created: n.created_at,
    read: n.read_at !== null,
    href: n.link || topicHref(n.topic, n.action_id),
    ...(n.action_id ? { actionId: n.action_id } : {}),
  }));
}

/** Open alerts the hub has not turned into a notification (yet), so a critical one is never missing. */
export function fromAlerts(alerts: readonly AlertInfo[], covered: ReadonlySet<string>, read: ReadonlySet<string>): ShellNotification[] {
  return alerts
    .filter((a) => a.state === 'open' && !covered.has(a.id))
    .map((a) => {
      const id = ALERT_PREFIX + a.id;
      return { id, kind: kindFor(a.topic ?? 'alerts', a.severity, null), severity: a.severity, source: a.topic ?? 'alerts', title: a.title, body: a.body || undefined, created: a.opened_at, read: read.has(id), href: a.link || href.alerts };
    });
}

/**
 * Hub notifications and alerts, then the derived ones, newest first. A derived approval is
 * dropped when the hub has a notification for the same action.
 */
export function mergeNotifications(server: readonly NotificationItem[] | undefined, alerts: readonly AlertInfo[] | undefined, derived: readonly ShellNotification[], read: ReadonlySet<string>): ShellNotification[] {
  const hub = fromServer(server ?? []).map((n) => (read.has(n.id) ? { ...n, read: true } : n));
  const actionIds = new Set((server ?? []).map((n) => n.action_id).filter((x): x is string => !!x));
  const alertIds = new Set((server ?? []).map((n) => n.alert_id).filter((x): x is string => !!x));
  const out = [...hub, ...fromAlerts(alerts ?? [], alertIds, read), ...derived.filter((d) => !(d.actionId && actionIds.has(d.actionId)))];
  return out.sort((x, y) => Date.parse(y.created) - Date.parse(x.created));
}

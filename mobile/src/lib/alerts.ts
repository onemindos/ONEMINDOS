// SPDX-License-Identifier: Apache-2.0
// What changed between two polls, phrased as phone notifications. Pure, so it is
// tested without a device. v0 delivery is poll + local notification; the push
// path (UnifiedPush on Android, an APNs ping on iOS, D-005) is in mobile/README.md.
import type { Action, InboxItem, NodeRecord, NodeStatus } from '../api/types';
import { actionTitle, principalLabel } from './approvals';

export interface Snapshot {
  actions: Record<string, Action['state']>;
  nodes: Record<string, { status: NodeStatus; hostname: string }>;
}

export interface Alert {
  /** Stable per event, so the same change never notifies twice. */
  id: string;
  title: string;
  body: string;
  /** Deep link target inside the app. */
  route: 'approvals' | 'nodes' | 'activity' | 'inbox';
}

export function snapshot(actions: Action[] | undefined, nodes: NodeRecord[] | undefined): Snapshot {
  return {
    actions: Object.fromEntries((actions ?? []).map((a) => [a.id, a.state])),
    nodes: Object.fromEntries((nodes ?? []).map((n) => [n.node_id, { status: n.status, hostname: n.hostname }])),
  };
}

const FINAL = new Set(['succeeded', 'failed', 'outcome_unknown', 'expired', 'cancelled']);

/**
 * Alerts for the change from `prev` to `next`. The first poll after launch
 * (`prev` undefined) raises nothing: the screens show the current state, and a
 * burst of old news on every app start would train people to ignore alerts.
 */
export function diffAlerts(prev: Snapshot | undefined, next: Snapshot, actions: Action[], nodes: NodeRecord[]): Alert[] {
  if (!prev) return [];
  const out: Alert[] = [];
  for (const a of actions) {
    const before = prev.actions[a.id];
    if (a.state === 'awaiting_approval' && before === undefined) {
      out.push({
        id: `action:${a.id}:requested`,
        title: 'Approval needed',
        body: `${principalLabel(a.requested_by)} asks: ${actionTitle(a)}`,
        route: 'approvals',
      });
    } else if (before !== undefined && before !== a.state && FINAL.has(a.state)) {
      out.push({
        id: `action:${a.id}:${a.state}`,
        title: `${actionTitle(a)}: ${a.state.replace(/_/g, ' ')}`,
        body: a.result?.message ?? `Was ${before.replace(/_/g, ' ')}.`,
        route: 'activity',
      });
    }
  }
  for (const n of nodes) {
    const before = prev.nodes[n.node_id];
    if (!before) {
      out.push({ id: `node:${n.node_id}:joined`, title: 'Node joined', body: `${n.hostname} is ${n.status}.`, route: 'nodes' });
    } else if (before.status !== n.status && (n.status === 'offline' || before.status === 'offline')) {
      // online <-> stale flaps are normal on a busy Wi-Fi; only offline changes alert.
      out.push({
        id: `node:${n.node_id}:${n.status}:${n.last_seen}`,
        title: n.status === 'offline' ? 'Node offline' : 'Node back',
        body: n.status === 'offline' ? `${n.hostname} has not reported for 2 minutes or more.` : `${n.hostname} is ${n.status} again.`,
        route: 'nodes',
      });
    }
  }
  return out;
}

/**
 * Hub inbox (§12.14) → phone notifications for items that are new since the last refresh and unread.
 * The first refresh (`seen` undefined) raises nothing, for the same reason as diffAlerts.
 * The text comes from the hub over HTTPS; nothing about it passed through a push service.
 */
export function inboxAlerts(seen: Set<string> | undefined, inbox: InboxItem[]): Alert[] {
  if (!seen) return [];
  return inbox
    .filter((n) => !seen.has(n.id) && !n.read_at)
    .map((n) => ({ id: `ntf:${n.id}`, title: n.title, body: n.body, route: n.action_id ? 'approvals' : 'inbox' }));
}

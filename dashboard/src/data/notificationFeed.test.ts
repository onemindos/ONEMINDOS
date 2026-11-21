// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import type { AlertInfo, NotificationItem } from '../api/wiring';
import { fromAlerts, fromServer, isServerId, mergeNotifications } from './notificationFeed';

const note = (o: Partial<NotificationItem>): NotificationItem => ({ id: 'n1', severity: 'info', topic: 'system', title: 'T', body: '', link: null, source: null, action_id: null, alert_id: null, created_at: '2026-11-21T10:00:00Z', read_at: null, ...o });
const alert = (o: Partial<AlertInfo>): AlertInfo => ({ schema: 'onemind.alert/v1', id: 'a1', type: 'disk.full', severity: 'critical', title: 'Disk almost full', body: '', subject: {}, state: 'open', occurrences: 1, flapping: false, opened_at: '2026-11-21T11:00:00Z', updated_at: '2026-11-21T11:00:00Z', resolved_at: null, fix: null, learn_more_url: null, topic: 'storage', link: null, acked_by: null, acked_at: null, ...o });

describe('notification feed', () => {
  it('maps hub notifications, read state and links', () => {
    const [a, b] = fromServer([note({ id: 'x', topic: 'backups', severity: 'critical', read_at: '2026-11-21T10:05:00Z' }), note({ id: 'y', topic: 'approvals', action_id: 'act 1' })]);
    expect(a).toMatchObject({ id: 'ntf:x', kind: 'backup_failed', read: true, href: '/settings/backups' });
    expect(b).toMatchObject({ kind: 'approval_waiting', actionId: 'act 1', href: '/approvals?highlight=act%201' });
    expect(isServerId(a!.id)).toBe(true);
  });

  it('shows an open critical alert that has no notification, once', () => {
    const covered = fromAlerts([alert({})], new Set(['a1']), new Set());
    expect(covered).toEqual([]);
    const [n] = fromAlerts([alert({}), alert({ id: 'a2', state: 'resolved' })], new Set(), new Set(['alr:a1']));
    expect(n).toMatchObject({ id: 'alr:a1', severity: 'critical', read: true, href: '/alerts' });
  });

  it('merges newest first and drops a derived approval the hub already reported', () => {
    const derived = [
      { id: 'act:act-1:waiting', kind: 'approval_waiting' as const, severity: 'warning' as const, source: 'approvals', title: 'dup', created: '2026-11-21T09:00:00Z', read: false, href: '/approvals', actionId: 'act-1' },
      { id: 'node:n:offline:1', kind: 'node_offline' as const, severity: 'warning' as const, source: 'fabric', title: 'n offline', created: '2026-11-21T08:00:00Z', read: false, href: '/nodes' },
    ];
    const out = mergeNotifications([note({ action_id: 'act-1', topic: 'approvals' })], [alert({})], derived, new Set());
    expect(out.map((n) => n.id)).toEqual(['alr:a1', 'ntf:n1', 'node:n:offline:1']);
  });

  it('never marks an unknown or missing source as a crash', () => {
    expect(mergeNotifications(undefined, undefined, [], new Set())).toEqual([]);
  });
});

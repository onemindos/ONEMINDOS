// SPDX-License-Identifier: Apache-2.0
// A ping carries ids only (D-005): whatever else it carries is never shown; the text comes from the box.
import * as Notifications from 'expo-notifications';
import type { InboxItem } from './api/types';
import { parsePing } from './lib/push';
import { lastPing, recordPing, showPinged } from './pushPings';
import { v0Api } from './test/fakes';

const ITEM = { id: 'ntf_01J9', title: 'Backup finished', body: 'Nightly backup to the USB disk worked.', action_id: null } as unknown as InboxItem;

describe('pings from the box', () => {
  beforeEach(() => jest.mocked(Notifications.scheduleNotificationAsync).mockClear());

  it('a ping with extra fields shows only the text fetched from /v1/notifications/{id}', async () => {
    const notification = jest.fn(async () => ITEM);
    const ping = parsePing({ notification_id: 'ntf_01J9', box_id: 'b', title: 'FROM THE PING', body: 'FROM THE PING' });
    await showPinged(v0Api({ notification }), ping?.id);
    expect(notification).toHaveBeenCalledWith('ntf_01J9');
    const shown = jest.mocked(Notifications.scheduleNotificationAsync).mock.calls.map((c) => c[0].content);
    expect(shown).toEqual([{ title: 'Backup finished', body: 'Nightly backup to the USB disk worked.', data: { route: 'inbox' } }]);
    expect(JSON.stringify(shown)).not.toContain('FROM THE PING');
  });

  it('uses approval buttons for approval pings and leaves them off other action pings', async () => {
    const approval = { ...ITEM, topic: 'approvals', action_id: 'act-waiting' };
    const completed = { ...approval, topic: 'apps', id: 'ntf-completed', action_id: 'act-done' };
    await showPinged(v0Api({ notification: async () => approval }), approval.id);
    await showPinged(v0Api({ notification: async () => completed }), completed.id);
    const [waiting, done] = jest.mocked(Notifications.scheduleNotificationAsync).mock.calls.map(([request]) => request.content);
    expect(waiting).toMatchObject({ categoryIdentifier: 'approval', data: { route: 'approvals', action_id: 'act-waiting' } });
    expect(done?.categoryIdentifier).toBeUndefined();
    expect(done?.data).toEqual({ route: 'inbox' });
  });

  it('when the box cannot be reached, says only that something is new', async () => {
    await showPinged(v0Api(), 'ntf_01J9');
    const [call] = jest.mocked(Notifications.scheduleNotificationAsync).mock.calls;
    expect(call?.[0].content.title).toBe('OneMind');
    expect(call?.[0].content.body).toMatch(/Something new on your box/);
  });

  it('remembers when the last ping arrived, taking the native service time when it is newer (app closed)', async () => {
    await recordPing(Date.parse('2026-11-22T08:00:00Z'));
    expect(await lastPing({ lastPingAt: () => null })).toBe('2026-11-22T08:00:00.000Z');
    expect(await lastPing({ lastPingAt: () => Date.parse('2026-11-22T09:30:00Z') })).toBe('2026-11-22T09:30:00.000Z');
    expect(await lastPing(undefined)).toBe('2026-11-22T08:00:00.000Z');
  });
});

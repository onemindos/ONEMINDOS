// SPDX-License-Identifier: Apache-2.0
// #682: marking read on the phone clears the dashboard bell within 2 s. The hub keeps the unread
// state and sends the reader's own streams a typed notification.read event; the bell reads the
// one summary call again and, because the summary moved, pulls the inbox.
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OneMindApi, NotificationSummary } from '../api/client';
import type { NotificationItem } from '../api/wiring';
import { SessionProvider } from '../session';
import { staleBy, summaryKey, useNotificationFeed } from './useNotificationFeed';

function note(id: string, read_at: string | null): NotificationItem {
  return { id, severity: 'warning', topic: 'system', title: 'Disk almost full', body: '', link: null, source: 'monitoring', action_id: null, alert_id: null, created_at: '2026-11-22T10:00:00Z', read_at } as NotificationItem;
}

/** A hub with one unread item for this person; `readElsewhere` is the phone marking it read. */
function hub() {
  let readAt: string | null = null;
  let emit: (type: string) => void = () => undefined;
  const calls = { notes: 0, summary: 0 };
  const api = {
    notifications: vi.fn(async () => { calls.notes += 1; return [note('n1', readAt)]; }),
    notificationSummary: vi.fn(async (): Promise<NotificationSummary> => {
      calls.summary += 1;
      return { unread: readAt ? 0 : 1, by_severity: { info: 0, warning: readAt ? 0 : 1, critical: 0 }, latest_created_at: '2026-11-22T10:00:00Z', last_read_at: readAt };
    }),
    alerts: vi.fn(async () => []),
    watchEvents: vi.fn((onEvent: (type: string) => void, signal: AbortSignal) => {
      emit = onEvent;
      return new Promise<void>((resolve) => signal.addEventListener('abort', () => resolve()));
    }),
    instance: vi.fn(async () => ({ name: 'box', version: '0', hub_node_id: null })),
    me: vi.fn(async () => ({ scopes: ['*'], capabilities: [] })),
  };
  return {
    api: api as unknown as OneMindApi,
    calls,
    readElsewhere: () => { readAt = '2026-11-22T10:05:00Z'; },
    emit: (type: string) => emit(type),
  };
}

function wrapper(api: OneMindApi) {
  window.sessionStorage.setItem('onemind.token', 'adult');
  return ({ children }: { children: ReactNode }) => (
    <SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'adult', kind: 'person', role: 'adult' }) }}>{children}</SessionProvider>
  );
}

afterEach(() => window.sessionStorage.clear());

describe('notification read state (#682)', () => {
  it('a read on another device clears the bell within 2 s through the typed event and the summary', async () => {
    const h = hub();
    const { result } = renderHook(() => useNotificationFeed(), { wrapper: wrapper(h.api) });
    await waitFor(() => expect(result.current.unread).toBe(1));
    await waitFor(() => expect(result.current.notifications?.[0]?.read_at).toBeNull());
    h.readElsewhere();
    const started = Date.now();
    act(() => h.emit('notification.read'));
    await waitFor(() => expect(result.current.notifications?.[0]?.read_at).not.toBeNull(), { timeout: 2000 });
    expect(Date.now() - started).toBeLessThan(2000);
    expect(result.current.unread).toBe(0);
  });

  it('events the bell does not show leave the inbox alone', async () => {
    const h = hub();
    const { result } = renderHook(() => useNotificationFeed(), { wrapper: wrapper(h.api) });
    await waitFor(() => expect(result.current.unread).toBe(1));
    const before = { ...h.calls };
    act(() => { h.emit('node.status'); h.emit('audit.appended'); h.emit('action.state_changed'); });
    await new Promise((r) => setTimeout(r, 1000));
    expect(h.calls).toEqual(before);
  });

  it('maps stream types to what they make stale, and keys the summary on what moves', () => {
    expect(staleBy('notification.read_all')).toEqual({ inbox: true, alerts: false });
    expect(staleBy('notification.created')).toEqual({ inbox: true, alerts: false });
    expect(staleBy('alert.opened')).toEqual({ inbox: false, alerts: true });
    expect(staleBy('stream.reset')).toEqual({ inbox: true, alerts: true });
    expect(staleBy('node.status')).toBeNull();
    expect(summaryKey(undefined)).toBe('');
    expect(summaryKey({ unread: 2, latest_created_at: 'a', last_read_at: null })).not.toBe(summaryKey({ unread: 2, latest_created_at: 'a', last_read_at: 'b' }));
  });
});

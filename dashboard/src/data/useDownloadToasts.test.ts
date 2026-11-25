// SPDX-License-Identifier: Apache-2.0
// #693: a clean download that reached Files shows one "Downloaded" toast; old items, read items,
// other notifications and held downloads (owners' alerts) do not.
import { renderHook } from '@testing-library/react';
import { vi } from 'vitest';
import type { NotificationItem } from '../api/wiring';
import { useDownloadToasts } from './useDownloadToasts';

const note = (id: string, over: Partial<NotificationItem> = {}): NotificationItem => ({
  id, severity: 'info', topic: 'storage', title: `Downloaded: ${id}.pdf`, body: `Saved to /Downloads/${id}.pdf in your Files.`,
  link: '/files', source: 'gateway', action_id: null, alert_id: null, created_at: '2026-11-22T12:00:00Z', read_at: null, ...over,
});

describe('Downloaded toast (#693)', () => {
  it('toasts each new delivered download once, with a way to Files', () => {
    const show = vi.fn();
    const openFiles = vi.fn();
    const { rerender } = renderHook(({ items }) => useDownloadToasts(items, show, openFiles), {
      initialProps: { items: undefined as NotificationItem[] | undefined },
    });
    rerender({ items: [note('old')] });
    expect(show).not.toHaveBeenCalled(); // there before the page loaded

    const held = note('held', { severity: 'critical', topic: 'security', title: 'Download held: eicar.com.txt', link: null });
    rerender({ items: [note('report'), held, note('seen', { read_at: '2026-11-22T12:01:00Z' }), note('old')] });
    expect(show).toHaveBeenCalledTimes(1);
    const [t] = show.mock.calls[0]!;
    expect(t.title).toBe('Downloaded');
    expect(t.body).toBe('report.pdf');
    t.action.onClick();
    expect(openFiles).toHaveBeenCalled();

    rerender({ items: [note('report'), held, note('old')] });
    expect(show).toHaveBeenCalledTimes(1); // never twice
  });
});

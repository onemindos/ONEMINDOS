// SPDX-License-Identifier: Apache-2.0
// #693: when the hub moves a clean browser download into the person's Files, the person gets an
// Inbox item (core notify/catalogue.py `files.download.delivered`: topic "storage", link "/files",
// title "Downloaded: <name>"). This shows it once as a "Downloaded" toast with a way to Files.
// Items already there when the page loads are not toasted again; held downloads never are (they
// are the owners' alerts, not the person's toast).
import { useEffect, useRef } from 'react';
import type { NotificationItem } from '../api/wiring';

export const DOWNLOADED_PREFIX = 'Downloaded: ';

export function isDownloaded(n: NotificationItem): boolean {
  return n.topic === 'storage' && n.link === '/files' && n.title.startsWith(DOWNLOADED_PREFIX) && n.read_at === null;
}

export interface DownloadToast { title: string; body?: string; action: { label: string; onClick: () => void } }

/** Calls `show` once for each new, unread Downloaded item; the first list only marks what is already there. */
export function useDownloadToasts(items: readonly NotificationItem[] | undefined, show: (t: DownloadToast) => void, openFiles: () => void) {
  const seen = useRef<Set<string> | null>(null);
  const latest = useRef({ show, openFiles });
  latest.current = { show, openFiles };
  useEffect(() => {
    if (!items) return;
    if (seen.current === null) {
      seen.current = new Set(items.map((n) => n.id));
      return;
    }
    for (const n of items) {
      if (seen.current.has(n.id)) continue;
      seen.current.add(n.id);
      if (!isDownloaded(n)) continue;
      latest.current.show({
        title: 'Downloaded',
        body: n.title.slice(DOWNLOADED_PREFIX.length),
        action: { label: 'Open Files', onClick: () => latest.current.openFiles() },
      });
    }
  }, [items]);
}

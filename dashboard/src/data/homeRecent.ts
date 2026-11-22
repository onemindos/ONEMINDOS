// SPDX-License-Identifier: Apache-2.0
import { useMemo, useRef } from 'react';
import { matchPath } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { SCREENS, navIdFor } from '../screens/registry';
import { useSignedIn } from '../session';
import { showsNav, type View } from '../shell/roles';

const MAX_RECENT = 8;
export const RECENT_UPDATED = 'onemind-home-recent';

export function recentItem(path: string, view: View, role?: string | null) {
  const screen = SCREENS.find((s) => s.id === navIdFor(path));
  if (!role || role === 'agent' || !screen || screen.path === '/' || view === 'unknown' || !showsNav(screen.id, view, role)) return;
  const app = /^\/(?:market|installed|browser)\/([a-z0-9][a-z0-9-]{0,62})$/.exec(path);
  if (app) return 'app:' + app[1];
  const subpage = screen.extra?.find((extra) => matchPath(extra.path, path));
  if (!screen.hidden && (matchPath(screen.path, path) || (subpage && (!subpage.owner || role === 'owner')))) {
    return 'sys:' + screen.id;
  }
}

export async function rememberVisit(api: OneMind['me']['home'], item: string): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    const { home, etag } = await api.get();
    const recent = home.recent ?? [];
    if (recent[0] === item) return;
    try {
      await api.save({ ...home, recent: [item, ...recent.filter((id) => id !== item)].slice(0, MAX_RECENT) }, etag);
      return;
    } catch (error) {
      if (!(error instanceof OneMindError && error.status === 412 && attempt < 2)) throw error;
    }
  }
}

/** Record a person's activated links in order. Direct loads, redirects and browser history stay read-only. */
export function useRecordVisit(view: View, role?: string | null) {
  const { token, mock } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token }), [token]);
  const queue = useRef(Promise.resolve());
  return (path: string) => {
    const item = recentItem(path.split(/[?#]/, 1)[0] ?? '', view, role);
    if (!item || mock) return;
    queue.current = queue.current.then(() => rememberVisit(sdk.me.home, item))
      .then(() => { window.dispatchEvent(new Event(RECENT_UPDATED)); })
      .catch(() => { /* Navigation still works if history cannot be saved. */ });
  };
}

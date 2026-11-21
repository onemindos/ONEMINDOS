// SPDX-License-Identifier: Apache-2.0
// Desktop or Console, per person (D-016, docs/learning/umbrelos-2-teardown.md §4). Desktop is the
// default: the wallpaper desktop with a dock, and every screen opens as a window over it. Console
// is the earlier sidebar layout, kept for people who prefer it. Stored in the person's browser
// slot only (a convenience, like the palette history); the hub copy comes with /v1/me/home.
import { useCallback, useMemo, useState } from 'react';
import { personStorage } from '../data/prefs';

export type LayoutMode = 'desktop' | 'console';
export const DEFAULT_LAYOUT_MODE: LayoutMode = 'desktop';
const KEY = 'shell.layout';

export function parseLayoutMode(raw: string | null | undefined): LayoutMode {
  return raw === 'console' || raw === 'desktop' ? raw : DEFAULT_LAYOUT_MODE;
}

export function layoutModeStore(personId: string, base?: Storage | null) {
  const s = base === undefined ? personStorage(personId) : personStorage(personId, base);
  return {
    load(): LayoutMode {
      try {
        return parseLayoutMode(s?.getItem(KEY));
      } catch {
        return DEFAULT_LAYOUT_MODE; // private windows can throw on storage access
      }
    },
    save(mode: LayoutMode): void {
      try {
        s?.setItem(KEY, mode);
      } catch {
        // not saved; the choice still applies until reload
      }
    },
  };
}

export function useLayoutMode(personId: string): [LayoutMode, (m: LayoutMode) => void] {
  const store = useMemo(() => layoutModeStore(personId), [personId]);
  const [mode, setMode] = useState<LayoutMode>(() => store.load());
  const set = useCallback(
    (m: LayoutMode) => {
      setMode(m);
      store.save(m);
    },
    [store],
  );
  return [mode, set];
}

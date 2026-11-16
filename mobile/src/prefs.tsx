// SPDX-License-Identifier: Apache-2.0
// UMB-P07 (#144): the person's Home preferences live on the hub, so the phone and the desktop match and a
// cleared browser loses nothing. Today the phone applies and edits the theme; the rest of the document
// (layout, dock, wallpaper) is carried through untouched when it saves, never dropped.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { OP } from './api/client';
import { ApiError, type HomeBody, type HomeView } from './api/types';
import { useSignedIn } from './session';
import { setThemeChoice } from './ui/theme';

type Theme = 'system' | 'light' | 'dark';

interface PrefsCtx {
  /** True when this hub keeps preferences (the route is in /openapi.json). */
  served: boolean;
  theme: Theme;
  /** Save a new theme; resolves with an error message when the hub refused, else undefined. */
  setTheme(theme: Theme): Promise<string | undefined>;
}

const Ctx = createContext<PrefsCtx>({ served: false, theme: 'system', setTheme: async () => undefined });

/** What PUT accepts: the document as read, without the read-only timestamp. */
function bodyOf(home: HomeView): HomeBody {
  const { updated_at: _ignored, ...rest } = home;
  return rest as HomeBody;
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const { api, features } = useSignedIn();
  const served = features.has(OP.homeGet);
  const [cur, setCur] = useState<{ home: HomeView; etag: string }>();

  useEffect(() => {
    if (!served) return;
    let live = true;
    api.home().then(
      (r) => live && setCur(r),
      () => undefined, // a hub that cannot answer keeps the phone's own theme
    );
    return () => void (live = false);
  }, [api, served]);

  const theme: Theme = cur?.home.appearance?.theme ?? 'system';
  useEffect(() => {
    setThemeChoice(theme);
    return () => setThemeChoice('system');
  }, [theme]);

  const setTheme = useCallback(
    async (next: Theme) => {
      if (!cur) return 'Preferences are not loaded yet.';
      const save = (from: { home: HomeView; etag: string }) =>
        api.saveHome({ ...bodyOf(from.home), // The hub always sends every appearance field; the generated type marks them optional only for their defaults.
          appearance: { ...from.home.appearance, theme: next } as HomeBody['appearance'] }, from.etag);
      try {
        setCur(await save(cur));
        return undefined;
      } catch (e) {
        if (e instanceof ApiError && e.status === 412) {
          // Changed on another screen meanwhile: read it again and apply this one change on top.
          try {
            setCur(await save(await api.home()));
            return undefined;
          } catch (e2) {
            return e2 instanceof Error ? e2.message : 'Could not save.';
          }
        }
        return e instanceof Error ? e.message : 'Could not save.';
      }
    },
    [api, cur],
  );

  const value = useMemo(() => ({ served, theme, setTheme }), [served, theme, setTheme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const usePrefs = () => useContext(Ctx);

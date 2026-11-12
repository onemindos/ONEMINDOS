// SPDX-License-Identifier: Apache-2.0
// Holds one person's appearance preferences, applies them to the document, and saves them
// through a PreferencesStore. Honest about where the copy came from (PRINCIPLES P2): the
// status says "this browser only", "your account", or "hub unreachable, showing the copy
// saved on this browser N ago".
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { storedTheme } from '../lib/theme';
import { applyPreferences, DEFAULT_PREFERENCES, msUntilNextSwitch, normalizePreferences, type AppearancePreferences } from './preferences';
import { PreferencesError, type PreferencesStore } from './store';

export type LoadPhase = 'loading' | 'ready' | 'error';
export type PrefsSource = 'hub' | 'local' | 'defaults';

export interface CustomizeStatus {
  phase: LoadPhase;
  /** Where the preferences on screen came from. */
  source: PrefsSource;
  /** RFC 3339 time of the copy on screen, or null for defaults. */
  updatedAt: string | null;
  /** True when the hub could not be read and a local copy is shown instead. */
  stale: boolean;
  loadError: string | null;
  saving: boolean;
  saveError: string | null;
  /** True when the last change is kept on this browser only. */
  localOnly: boolean;
}

export interface CustomizeContextValue {
  prefs: AppearancePreferences;
  status: CustomizeStatus;
  wallpaperImage: string | null;
  update: (patch: Partial<AppearancePreferences>) => void;
  /** Replace everything (reset, undo). */
  replace: (prefs: AppearancePreferences) => void;
  setWallpaperImage: (dataUrl: string | null, colors?: string[]) => Promise<void>;
  retry: () => void;
  storeKind: PreferencesStore['kind'];
  /** The hub's clock for "N ago" labels (P2). */
  now: () => Date;
}

const Ctx = createContext<CustomizeContextValue | null>(null);

export function useCustomize(): CustomizeContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useCustomize() needs a <CustomizeProvider> above it.');
  return v;
}

/** Like useCustomize(), but null outside a provider (for optional consumers). */
export function useOptionalCustomize(): CustomizeContextValue | null {
  return useContext(Ctx);
}

export interface CustomizeProviderProps {
  /** Primary store: the hub (§12, pending) or this browser. */
  store: PreferencesStore;
  /** Fallback copy used when `store` cannot be read or written (normally a LocalPreferencesStore). */
  cache?: PreferencesStore;
  /** Clock; the dashboard passes the hub's. */
  now?: () => Date;
  /** Apply to `document.documentElement` (default true). Tests and previews can turn it off. */
  apply?: boolean;
  /** Debounce for saves, ms. */
  saveDelay?: number;
  children?: ReactNode;
}

const message = (e: unknown) => (e instanceof PreferencesError || e instanceof Error ? e.message : 'Something went wrong.');

function prefersReducedTransparency(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-transparency: reduce)').matches;
  } catch {
    return false;
  }
}

export function CustomizeProvider({ store, cache, now = () => new Date(), apply = true, saveDelay = 400, children }: CustomizeProviderProps) {
  const [prefs, setPrefs] = useState<AppearancePreferences>(DEFAULT_PREFERENCES);
  const [wallpaperImage, setImage] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<CustomizeStatus>({
    phase: 'loading',
    source: 'defaults',
    updatedAt: null,
    stale: false,
    loadError: null,
    saving: false,
    saveError: null,
    localOnly: store.kind === 'local',
  });
  const nowRef = useRef(now);
  nowRef.current = now;

  // Load: primary store first, then the cache, then defaults. Every path ends "ready" or "error"
  // with a sentence that says which copy is on screen.
  useEffect(() => {
    let live = true;
    setStatus((s) => ({ ...s, phase: 'loading', loadError: null }));
    (async () => {
      try {
        const got = await store.load();
        const img = await store.loadWallpaperImage().catch(() => null);
        if (!live) return;
        const first = got.updatedAt === null;
        setPrefs(first ? { ...got.prefs, theme: storedTheme() } : got.prefs);
        setImage(img);
        setStatus((s) => ({ ...s, phase: 'ready', source: first ? 'defaults' : store.kind, updatedAt: got.updatedAt, stale: false, localOnly: store.kind === 'local' }));
        if (cache && !first) cache.save(got.prefs).catch(() => undefined);
      } catch (e) {
        if (!cache) {
          if (!live) return;
          setStatus((s) => ({ ...s, phase: 'error', loadError: message(e) }));
          return;
        }
        try {
          const got = await cache.load();
          const img = await cache.loadWallpaperImage().catch(() => null);
          if (!live) return;
          setPrefs(got.updatedAt === null ? { ...got.prefs, theme: storedTheme() } : got.prefs);
          setImage(img);
          setStatus((s) => ({
            ...s,
            phase: 'ready',
            source: got.updatedAt ? 'local' : 'defaults',
            updatedAt: got.updatedAt,
            stale: true,
            loadError: message(e),
            localOnly: true,
          }));
        } catch (e2) {
          if (!live) return;
          setStatus((s) => ({ ...s, phase: 'error', loadError: `${message(e)} ${message(e2)}` }));
        }
      }
    })();
    return () => {
      live = false;
    };
  }, [store, cache, attempt]);

  // Apply whenever preferences change; re-apply at the next scheduled theme switch and when
  // the system transparency setting changes.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!apply || status.phase === 'loading') return;
    applyPreferences(prefs, { now: nowRef.current(), systemReducedTransparency: prefersReducedTransparency() });
    if (prefs.theme !== 'schedule') return;
    const t = window.setTimeout(() => setTick((n) => n + 1), msUntilNextSwitch(prefs.schedule, nowRef.current()));
    return () => window.clearTimeout(t);
  }, [prefs, apply, status.phase, tick]);

  useEffect(() => {
    if (!apply) return;
    let mq: MediaQueryList | null = null;
    try {
      mq = window.matchMedia('(prefers-reduced-transparency: reduce)');
    } catch {
      return;
    }
    const on = () => setTick((n) => n + 1);
    mq.addEventListener?.('change', on);
    return () => mq?.removeEventListener?.('change', on);
  }, [apply]);

  // Debounced save. Falls back to the cache and says the change is on this browser only.
  const pending = useRef<AppearancePreferences | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const flush = useCallback(async () => {
    const p = pending.current;
    pending.current = null;
    if (!p) return;
    setStatus((s) => ({ ...s, saving: true, saveError: null }));
    try {
      const saved = await store.save(p);
      setStatus((s) => ({ ...s, saving: false, source: store.kind, updatedAt: saved.updatedAt, stale: false, localOnly: store.kind === 'local' }));
      if (cache) cache.save(p).catch(() => undefined);
    } catch (e) {
      if (cache) {
        try {
          const saved = await cache.save(p);
          setStatus((s) => ({ ...s, saving: false, source: 'local', updatedAt: saved.updatedAt, saveError: `${message(e)} Kept on this browser for now.`, localOnly: true }));
          return;
        } catch {
          /* fall through */
        }
      }
      setStatus((s) => ({ ...s, saving: false, saveError: message(e) }));
    }
  }, [store, cache]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const commit = useCallback(
    (next: AppearancePreferences) => {
      setPrefs(next);
      pending.current = next;
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush(), saveDelay);
    },
    [flush, saveDelay],
  );

  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  const update = useCallback((patch: Partial<AppearancePreferences>) => commit(normalizePreferences({ ...prefsRef.current, ...patch })), [commit]);
  const replace = useCallback((p: AppearancePreferences) => commit(normalizePreferences(p)), [commit]);

  const setWallpaperImage = useCallback(
    async (dataUrl: string | null, colors: string[] = []) => {
      try {
        await store.saveWallpaperImage(dataUrl);
      } catch (e) {
        if (!cache) throw e;
        await cache.saveWallpaperImage(dataUrl);
      }
      setImage(dataUrl);
      const cur = prefsRef.current;
      if (dataUrl) commit(normalizePreferences({ ...cur, wallpaper: 'custom', customWallpaperColors: colors }));
      else commit(normalizePreferences({ ...cur, wallpaper: cur.wallpaper === 'custom' ? DEFAULT_PREFERENCES.wallpaper : cur.wallpaper, customWallpaperColors: [] }));
    },
    [store, cache, commit],
  );

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const value = useMemo<CustomizeContextValue>(
    () => ({ prefs, status, wallpaperImage, update, replace, setWallpaperImage, retry, storeKind: store.kind, now: () => nowRef.current() }),
    [prefs, status, wallpaperImage, update, replace, setWallpaperImage, retry, store.kind],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

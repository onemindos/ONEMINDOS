// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { SETTINGS_SECTIONS, useToast } from '@onemind/ui';
import { PRO_SETTINGS } from '../proSettings';
import { personStorage } from '../../data/prefs';
import { useSignedIn } from '../../session';
import { useShell } from '../Shell';
import { showsNav } from '../roles';
import { routeFor } from './ScreenRoutes';
import { close, LIMIT, minimise, open, restore, save, top, type Windows } from './store';

const query = '(max-width: 720px)';
function watchWidth(notify: () => void) {
  const media = window.matchMedia?.(query);
  media?.addEventListener?.('change', notify);
  return () => media?.removeEventListener?.('change', notify);
}
const isNarrow = () => window.matchMedia?.(query).matches ?? false;

export function useWindows() {
  const { api, principal } = useSignedIn();
  const [hubPerson, setHubPerson] = useState<string>();
  // Live sessions rotate tokens. Only the principal returned by the hub owns this slot.
  useEffect(() => {
    if (principal) return;
    let live = true;
    let timer: number;
    const read = () => api.me().then(me => {
      if (live) setHubPerson(me.principal.id);
    }, () => { if (live) timer = window.setTimeout(read, 3000); });
    void read();
    return () => { live = false; window.clearTimeout(timer); };
  }, [api, principal]);
  const person = principal?.id ?? hubPerson;
  const { view, role } = useShell();
  const toast = useToast();
  const storage = useMemo(() => person ? personStorage(person) : null, [person]);
  const narrow = useSyncExternalStore(watchWidth, isNarrow, () => false);
  const { pathname, search, hash } = useLocation();
  const path = pathname + search + hash;
  const navigate = useNavigate();
  const [windows, setWindows] = useState<Windows>([]);
  const latest = useRef(windows);
  const loaded = useRef<string | undefined>(undefined);
  const allowed = useCallback((path: string) => {
    const route = routeFor(path);
    if (!route || (route.owner && role !== 'owner') || !showsNav(route.screen.id, view, role)) return;
    if (route.screen.id === 'settings' && route.section) {
      const section = SETTINGS_SECTIONS.find(s => s.id === route.section);
      if (!section || (view !== 'pro' && PRO_SETTINGS.has(section.id))) return;
    }
    if (route.screen.id === 'troubleshoot' && role !== 'owner') return;
    return route.screen.id;
  }, [role, view]);

  const update = useCallback((next: Windows) => {
    latest.current = next;
    setWindows(next);
    if (loaded.current !== person) return;
    try {
      storage?.setItem('shell.windows', save(next.filter(w => allowed(w.path))));
    } catch { /* Private or full storage still permits this visit. */ }
  }, [allowed, person, storage]);

  useLayoutEffect(() => {
    if (role === undefined || !person) {
      // The current URL renders normally while identity resolves. Leave the saved session untouched.
      const match = routeFor(path);
      const next = match ? open(latest.current, match.screen.id, path) : [];
      latest.current = next;
      setWindows(next);
      return;
    }
    const first = loaded.current !== person;
    let next = latest.current;
    if (first) {
      let raw = null;
      try { raw = storage?.getItem('shell.windows') ?? null; } catch { /* Storage unavailable. */ }
      next = restore(raw, allowed);
      loaded.current = person;
    } else {
      next = next.filter(w => allowed(w.path));
    }
    const match = routeFor(path);
    if (pathname !== '/' && match) {
      if (next.length === LIMIT && !next.some(w => w.id === match.screen.id)) {
        toast.show({ title: `Closed ${routeFor(next[0]!.path)?.screen.title} to make room` });
      }
      next = open(next, match.screen.id, path);
    } else if (pathname === '/' && first && top(next)) {
      navigate(top(next)!.path, { replace: true });
    } else if (pathname === '/') {
      next = next.map(w => ({ ...w, minimised: true }));
    }
    if (narrow) {
      const visible = top(next);
      next = visible ? [visible] : next.slice(-1);
    }
    update(next);
  // URL transitions, view changes and display size drive the stack. Frame changes leave the URL alone.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, pathname, person, view, role, narrow, storage, allowed, update]);

  function dismiss(id: string, minimiseOnly = false) {
    const next = (minimiseOnly ? minimise : close)(latest.current, id);
    update(next);
    navigate(top(next)?.path ?? '/');
  }
  return { windows, narrow, update, dismiss, active: pathname === '/' ? undefined : top(windows)?.id };
}

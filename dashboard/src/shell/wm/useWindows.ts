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
import { close, LIMIT, minimise, onWorkspace, open, restore, save, sendTo, top, validWorkspace, type Rect, type Windows } from './store';
import { isLayout, tile, type Layout } from './tiling';

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
  const [workspace, setWorkspaceState] = useState(0);
  const wsRef = useRef(0);
  // Opt-in and remembered per person; null is off. Never applied on a phone.
  const [tiling, setTilingState] = useState<Layout | null>(null);
  const lastLayout = useRef<Layout>('halves');
  const order = useRef<string[]>([]);
  const loaded = useRef<string | undefined>(undefined);
  const pendingRestore = useRef<string | undefined>(undefined);
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
      try {
        const saved = Number(storage?.getItem('shell.workspace'));
        wsRef.current = validWorkspace(saved) ? saved : 0;
        const layout = storage?.getItem('shell.tiling');
        setTilingState(isLayout(layout) ? layout : null);
        if (isLayout(layout)) lastLayout.current = layout;
      } catch { wsRef.current = 0; }
      setWorkspaceState(wsRef.current);
      pendingRestore.current = pathname === '/' ? top(next, wsRef.current)?.path : undefined;
    } else {
      next = next.filter(w => allowed(w.path));
    }
    const match = routeFor(path);
    if (pathname !== '/') pendingRestore.current = undefined;
    if (pathname !== '/' && match) {
      if (next.length === LIMIT && !next.some(w => w.id === match.screen.id)) {
        toast.show({ title: `Closed ${routeFor(next[0]!.path)?.screen.title} to make room` });
      }
      next = open(next, match.screen.id, path, wsRef.current);
    } else if (pathname === '/' && (!pendingRestore.current || !allowed(pendingRestore.current))) {
      // A saved window this person may no longer open is not restored.
      pendingRestore.current = undefined;
    }
    // At "/" the desktop has focus: the windows stay where they are over it (Atlas), none of them active.
    if (narrow) {
      const visible = top(next, wsRef.current);
      next = visible ? [{ ...visible, ws: wsRef.current }] : next.slice(-1);
    }
    update(next);
  // URL transitions, view changes and display size drive the stack. Frame changes leave the URL alone.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, pathname, person, view, role, narrow, storage, allowed, update]);

  // A parent router subscribes during its layout effect. Navigate after that
  // subscription and keep the saved windows open until the restored URL commits.
  useEffect(() => {
    const target = pendingRestore.current;
    if (pathname === '/' && person && role !== undefined && target) {
      navigate(target, { replace: true });
    }
  }, [navigate, pathname, person, role, view]);

  function dismiss(id: string, minimiseOnly = false) {
    const next = (minimiseOnly ? minimise : close)(latest.current, id);
    update(next);
    navigate(top(next, wsRef.current)?.path ?? '/');
  }
  function remember(key: string, value: string) {
    try { storage?.setItem(key, value); } catch { /* Private or full storage still permits this visit. */ }
  }
  function switchWorkspace(n: number) {
    if (!validWorkspace(n) || n === wsRef.current) return;
    wsRef.current = n;
    setWorkspaceState(n);
    remember('shell.workspace', String(n));
    // The windows of that workspace keep their place; a minimised one comes back with the last focused.
    navigate(onWorkspace(latest.current, n).at(-1)?.path ?? '/');
  }
  function sendWindow(id: string, n: number) {
    if (!validWorkspace(n)) return;
    const next = sendTo(latest.current, id, n);
    update(next);
    if (id === top(latest.current, wsRef.current)?.id) navigate(top(next, wsRef.current)?.path ?? '/');
  }
  function setTiling(layout: Layout | null) {
    if (layout) lastLayout.current = layout;
    setTilingState(layout);
    remember('shell.tiling', layout ?? 'off');
  }
  const toggleTiling = () => setTiling(tiling ? null : lastLayout.current);
  // Windows keep a stable order (first opened first), so focusing one never reshuffles the tiles.
  const here = windows.filter(w => w.ws === workspace);
  order.current = [...order.current.filter(id => windows.some(w => w.id === id)), ...windows.map(w => w.id).filter(id => !order.current.includes(id))];
  const visible = order.current.filter(id => here.some(w => w.id === id && !w.minimised));
  const tiled = visible.filter(id => !here.find(w => w.id === id)!.maximised);
  const rects = tiling && !narrow ? tile(tiling, tiled.length) : [];
  const tiles: Record<string, Rect> = Object.fromEntries(rects.map((rect, i) => [tiled[i]!, rect]));
  function cycle(step: 1 | -1) {
    const live = visible.map(id => here.find(w => w.id === id)!);
    if (live.length < 2) return false;
    const at = live.findIndex(w => w.id === (pathname === '/' ? undefined : top(windows, workspace)?.id));
    navigate(live[(at + step + live.length) % live.length]!.path);
  }
  const active = pathname === '/' ? undefined : top(windows, workspace)?.id;
  return { windows, narrow, update, dismiss, active, workspace, switchWorkspace, sendWindow, tiling, setTiling, toggleTiling, tiles, cycle };
}

// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react';
import { createRoutesFromElements, matchRoutes, Navigate, Route, Routes } from 'react-router';
import { StateView } from '@onemind/ui';
import { SCREENS } from '../../screens/registry';
import type { ScreenLoader } from '../../screens/types';
import { OwnerOnly, ProOnly } from '../ProOnly';

// One lazy component per distinct loader, made once so a re-render never remounts a screen.
const lazies = new Map<ScreenLoader, LazyExoticComponent<ComponentType>>();
function lazyOf(load: ScreenLoader) {
  let c = lazies.get(load);
  if (!c) lazies.set(load, (c = lazy(load)));
  return c;
}

/** The routes of every screen in the registry (src/screens/<id>/screen.ts). */
function screenRoutes() {
  return SCREENS.flatMap((s) => {
    const rel = (path: string) => path.replace(/^\//, '');
    const wrap = (load: ScreenLoader, ownerOnly?: string) => {
      const Page = lazyOf(load);
      if (ownerOnly) return <OwnerOnly title={ownerOnly}><Page /></OwnerOnly>;
      return s.pro ? <ProOnly title={s.title}><Page /></ProOnly> : <Page />;
    };
    return [
      s.path === '/' ? <Route key={s.id} index element={wrap(s.load)} /> : <Route handle={{ screen: s }} key={s.id} path={rel(s.path)} element={wrap(s.load)} />,
      ...(s.extra ?? []).map((e) => <Route handle={{ screen: s, owner: e.owner }} key={`${s.id}${e.path}`} path={rel(e.path)} element={wrap(e.load ?? s.load, e.owner)} />),
      ...(s.redirects ?? []).map((r) => <Route key={`${s.id}${r.from}`} path={rel(r.from)} element={<Navigate to={r.to} replace />} />),
    ];
  });
}

const screens = screenRoutes();
const routes = createRoutesFromElements(screens);
export function routeFor(path: string) {
  const match = matchRoutes(routes, path)?.at(-1);
  const handle = match?.route.handle as { screen: (typeof SCREENS)[number]; owner?: string } | undefined;
  return handle && { ...handle, section: match?.params.section };
}
export function ScreenRoutes({ location }: { location?: string }) {
  return <Suspense fallback={<StateView state="loading" what="This screen" skeleton="list" />}>
    <Routes location={location}>{screens}<Route path="*" element={<Navigate to="/" replace />} /></Routes>
  </Suspense>;
}

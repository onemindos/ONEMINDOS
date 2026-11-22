// SPDX-License-Identifier: Apache-2.0
// Route table. Signed out: the sign-in screen. Signed in: per-person appearance (CustomizeProvider),
// one shared hub poll (HubProvider), the shell, and the screens of docs/design/IA.md.
import { useEffect, useMemo } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react';
import { CustomizeProvider, StateView, ToastProvider, WallpaperLayer, clearPreferences } from '@onemind/ui';
import { ErrorBoundary } from './components/ErrorBoundary';
import { HubProvider, useHub } from './data/hub';
import { preferenceStores } from './data/prefs';
import { FirstRun, useWizardPending } from './pages/FirstRun';
import { OwnerOnly, ProOnly } from './shell/ProOnly';
import { SignIn } from './pages/SignIn';
import { LocaleProvider } from './i18n/LocaleProvider';
import { useSession, useSignedIn } from './session';
import { Shell } from './shell/Shell';
import { SCREENS } from './screens/registry';
import type { ScreenLoader } from './screens/types';

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
      s.path === '/' ? <Route key={s.id} index element={wrap(s.load)} /> : <Route key={s.id} path={rel(s.path)} element={wrap(s.load)} />,
      ...(s.extra ?? []).map((e) => <Route key={`${s.id}${e.path}`} path={rel(e.path)} element={wrap(e.load ?? s.load, e.owner)} />),
      ...(s.redirects ?? []).map((r) => <Route key={`${s.id}${r.from}`} path={rel(r.from)} element={<Navigate to={r.to} replace />} />),
    ];
  });
}

function Appearance({ children }: { children: React.ReactNode }) {
  const { person, token, api } = useSignedIn();
  const hub = useHub();
  const features = hub.instance.data?.features;
  const stores = useMemo(() => preferenceStores(person, { features, token }), [person, features, token]);
  useEffect(() => () => clearPreferences(), []);
  return (
    <CustomizeProvider key={`${person}:${stores.store.kind}`} store={stores.store} cache={stores.cache} now={() => new Date(Date.now() + (api.hubOffsetMs() ?? 0))}>
      <WallpaperLayer />
      {children}
    </CustomizeProvider>
  );
}

export function SignedInApp() {
  const [wizard, setWizard] = useWizardPending();
  return (
    <HubProvider>
      <Appearance>
        {wizard === undefined ? (
          <p role="status">Checking first-run setup…</p>
        ) : wizard ? (
          <FirstRun onDone={() => setWizard(false)} />
        ) : (
        <Shell>
          <Suspense fallback={<StateView state="loading" what="This screen" skeleton="list" />}>
            <Routes>
              {screenRoutes()}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </Shell>
        )}
      </Appearance>
    </HubProvider>
  );
}

export function App({ mock }: { mock: boolean }) {
  const { session } = useSession();
  return (
    <LocaleProvider person={session?.person ?? null}>
      <ErrorBoundary>
        <ToastProvider>{session ? <SignedInApp /> : <SignIn mock={mock} />}</ToastProvider>
      </ErrorBoundary>
    </LocaleProvider>
  );
}

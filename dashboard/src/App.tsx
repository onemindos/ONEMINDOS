// SPDX-License-Identifier: Apache-2.0
// Route table. Signed out: the sign-in screen. Signed in: per-person appearance (CustomizeProvider),
// one shared hub poll (HubProvider), the shell, and the screens of docs/design/IA.md.
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { ScreenRoutes } from './shell/wm/ScreenRoutes';
import { CustomizeProvider, ToastProvider, WallpaperLayer, clearPreferences } from '@onemind/ui';
import { ErrorBoundary } from './components/ErrorBoundary';
import { UpdateNeeded } from './components/UpdateNeeded';
import { useUpdateNeeded } from './lib/protocol';
import { HubProvider, useHub } from './data/hub';
import { preferenceStores } from './data/prefs';
import { FirstRun, useWizardPending } from './pages/FirstRun';
import { SignIn } from './pages/SignIn';
import { LocaleProvider } from './i18n/LocaleProvider';
import { useSession, useSignedIn } from './session';
import { BoxCodeHost } from './lib/boxcode';
import { VerificationHost } from './lib/verification';
import { Shell } from './shell/Shell';
import { LockScreen } from './shell/lock/LockScreen';

const IdentitySetup = lazy(() => import('./pages/IdentitySetup').then(({ IdentitySetup }) => ({ default: IdentitySetup })));

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

function Appliance() {
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
          <ScreenRoutes />
        </Shell>
        )}
      </Appearance>
    </HubProvider>
  );
}

export function SignedInApp({ newMember, onEnrolled }: { newMember?: boolean; onEnrolled?: () => void } = {}) {
  const { setupPending } = useSignedIn();
  const [setupDone, setSetupDone] = useState(false);
  const waiting = <p role="status">Checking account setup…</p>;
  if (setupPending === undefined) return waiting;
  const owner = setupPending && !setupDone;
  if (owner || newMember) return <Suspense fallback={waiting}>
    <IdentitySetup owner={owner} onDone={owner ? () => setSetupDone(true) : () => onEnrolled?.()} />
  </Suspense>;
  return <Appliance />;
}

export function App({ mock }: { mock: boolean }) {
  const { session, locked } = useSession();
  const [newMember, setNewMember] = useState(false);
  useEffect(() => { if (!session) setNewMember(false); }, [session]);
  const update = useUpdateNeeded();
  return (
    <LocaleProvider person={session?.person ?? null}>
      <ErrorBoundary>
        <ToastProvider key={locked ? 'locked' : 'unlocked'}>
          {session && <><BoxCodeHost /><VerificationHost /></>}
          {locked ? <LockScreen summary={locked} mock={mock} /> : update ? <UpdateNeeded state={update} /> : session ? <SignedInApp key={session.token} newMember={newMember} onEnrolled={() => setNewMember(false)} /> : <SignIn mock={mock} onEnrolled={() => setNewMember(true)} />}
        </ToastProvider>
      </ErrorBoundary>
    </LocaleProvider>
  );
}

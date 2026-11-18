// SPDX-License-Identifier: Apache-2.0
// Route table. Signed out: the sign-in screen. Signed in: per-person appearance (CustomizeProvider),
// one shared hub poll (HubProvider), the shell, and the screens of docs/design/IA.md.
import { useEffect, useMemo, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { CustomizeProvider, ToastProvider, WallpaperLayer, clearPreferences } from '@onemind/ui';
import { ErrorBoundary } from './components/ErrorBoundary';
import { HubProvider, useHub } from './data/hub';
import { preferenceStores } from './data/prefs';
import { Activity } from './pages/Activity';
import { Alerts } from './pages/Alerts';
import { Storage } from './pages/Storage';
import { Backups } from './pages/Backups';
import { Coming } from './pages/Coming';
import { FirstRun, wizardPending } from './pages/FirstRun';
import { Approvals } from './pages/Approvals';
import { Home } from './pages/Home';
import { Installed } from './pages/Installed';
import { Market } from './pages/Market';
import { Nodes } from './pages/Nodes';
import { ControlHub } from './pages/ControlHub';
import { Agents } from './pages/Agents';
import { ProOnly } from './shell/ProOnly';
import { Settings } from './pages/Settings';
import { SignIn } from './pages/SignIn';
import { useSession, useSignedIn } from './session';
import { Shell } from './shell/Shell';

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
  const [wizard, setWizard] = useState(wizardPending);
  return (
    <HubProvider>
      <Appearance>
        {wizard ? (
          <FirstRun onDone={() => setWizard(false)} />
        ) : (
        <Shell>
          <Routes>
            <Route index element={<Home />} />
            <Route path="market" element={<Market />} />
            <Route path="market/:appId" element={<Market />} />
            <Route path="installed" element={<Installed />} />
            <Route path="installed/:appId" element={<Installed />} />
            <Route path="approvals" element={<Approvals />} />
            <Route path="activity" element={<Activity />} />
            <Route path="nodes" element={<ProOnly title="Nodes"><Nodes /></ProOnly>} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="storage" element={<ProOnly title="Storage"><Storage /></ProOnly>} />
            <Route path="settings/storage" element={<Navigate to="/storage" replace />} />
            <Route path="backups" element={<ProOnly title="Backups"><Backups /></ProOnly>} />
            <Route path="settings/backups" element={<Navigate to="/backups" replace />} />
            <Route path="coming" element={<Coming />} />
            <Route path="control-hub" element={<ProOnly title="Control Hub"><ControlHub /></ProOnly>} />
            <Route path="agents" element={<ProOnly title="AI & Agents"><Agents /></ProOnly>} />
            <Route path="settings" element={<Settings />} />
            <Route path="settings/:section" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
        )}
      </Appearance>
    </HubProvider>
  );
}

export function App({ mock }: { mock: boolean }) {
  const { session } = useSession();
  return (
    <ErrorBoundary>
      <ToastProvider>{session ? <SignedInApp /> : <SignIn mock={mock} />}</ToastProvider>
    </ErrorBoundary>
  );
}

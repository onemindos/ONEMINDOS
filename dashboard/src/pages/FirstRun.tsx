// SPDX-License-Identifier: Apache-2.0
// The first-run wizard of @onemind/ui (Onboarding), wired. The gateway decides when it opens
// (GET /v1/onboarding/state: settings saved and, once a backup destination exists, the kit confirmed),
// so a reload or a second browser lands in the same place. Real effects only:
//  - Owner identity and its recovery kit are handled before opening this settings wizard (D-034).
//  - Each starter app the owner ticks becomes an `app.install` REQUEST in Approvals. Nothing is
//    installed by the wizard (AI and automation never actuate; the owner approves each one).
//  - The recovery kit step claims the owner key after verified approval and confirms two typed-back groups.
//    The key lives only in the step's memory, is never stored, and is never logged or put in a URL.
//  - Each starter install shows its read-only plan first; the request carries that plan's hash, so the
//    approval is bound to exactly what was shown.
//  - The place (name, the owner's address text, a position given offline) is saved as the box's first
//    site through POST /v1/sites, so the desktop Map opens on it. Setup ends on that Map when it exists.
// Software settings persist through §12.41. Backup configuration stays in §12.12.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Onboarding, applyTheme, cleanAddress, siteAnchors, siteIdFor, useToast, type OnboardingDraft, type SavedPlace, type StarterApp } from '@onemind/ui';
import type { components } from '@onemind/sdk';
import { ApiError, type CatalogApp } from '../api/types';
import type { BackupDestinationRecord, FirstRunSettings, FirstRunSettingsBody, FirstRunState } from '../api/client';
import { categorySlug, deployClass } from '../data/adapters';
import { useHub } from '../data/hub';
import { recoveryKit } from '../data/recoveryKit';
import { useGateway, viaSdk } from '../lib/gateway';
import { SCREENS } from '../screens/registry';
import { useSignedIn } from '../session';
import { RecoverRemoteApprovals } from './SignInKeys';

export function toStarterApp(a: CatalogApp): StarterApp | undefined {
  const category = categorySlug(a.category);
  if (!category || a.installed || a.tier === 'blocked') return undefined;
  return { id: a.id, name: a.name || a.id, tagline: a.description ?? '', category, deployClass: deployClass(a.tier), minMemoryMb: 0 };
}

/** undefined while asking the gateway. A failed or refused answer (a non-owner gets 403) never traps anyone in the wizard. */
export function useWizardPending(): [boolean | undefined, (pending: boolean) => void] {
  const { api } = useSignedIn();
  const [pending, setPending] = useState<boolean>();
  useEffect(() => {
    let live = true;
    api.onboardingState().then((s) => { if (live) setPending(!s.complete); }, () => { if (live) setPending(false); });
    return () => { live = false; };
  }, [api]);
  return [pending, setPending];
}

type GeoSite = components['schemas']['GeoSite'];

/** The box's first site from the wizard's place: its name, the owner's address text and three grid points. */
export function firstSite(d: Pick<OnboardingDraft, 'placeName' | 'address' | 'location'>): GeoSite | undefined {
  if (!d.location) return undefined;
  const name = d.placeName.trim() || 'Home';
  const address = cleanAddress(d.address).trim();
  return { id: siteIdFor(name), name, ...(address ? { address } : {}), floors: [], areas: [], anchors: siteAnchors(d.location) };
}

/** What the owner is shown after the save: the site as the gateway holds it. */
export function placeOf(status: SavedPlace['status'], site: GeoSite): SavedPlace {
  const origin = site.anchors.find((a) => a.x === 0 && a.y === 0);
  return { status, name: site.name, address: site.address ?? null, ...(origin ? { location: { lat: origin.lat, lon: origin.lon } } : {}) };
}

/** Setup ends on the desktop Map when this build has it (#1340); Approvals or Home otherwise. */
export function landingAfterSetup(requests: number, screens: ReadonlyArray<{ path: string }> = SCREENS): string {
  if (screens.some((s) => s.path === '/map')) return '/map';
  return requests ? '/approvals' : '/';
}

export function FirstRun({ onDone }: { onDone: () => void }) {
  const { api, account, anon, token, mock } = useSignedIn();
  const sdk = useGateway(token);
  const hub = useHub();
  const toast = useToast();
  const navigate = useNavigate();
  const apps = useMemo(() => (hub.apps.data ?? []).map(toStarterApp).filter((a): a is StarterApp => !!a), [hub.apps.data]);
  const [loaded, setLoaded] = useState<{ settings: FirstRunSettings; destinations: BackupDestinationRecord[]; state: FirstRunState }>();
  const previewed = useRef(new Map<string, string>());
  const landingRef = useRef('/');
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const [headless, setHeadless] = useState(false);
  const [recover, setRecover] = useState(false);
  useEffect(() => {
    let live = true;
    setError(undefined);
    void Promise.all([api.onboardingSettings(), api.backupDestinations(), api.onboardingState()]).then(([settings, destinations, state]) => {
      if (live) setLoaded({ settings, destinations, state });
    }).catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : 'Could not load settings.'); });
    void anon?.setupStatus?.().then((s) => { if (live) setHeadless(!s.screen); }, () => undefined);
    return () => { live = false; };
  }, [api, anon, attempt]);
  if (error) return <div role="alert">{error} <button onClick={() => setAttempt((x) => x + 1)}>Try again</button></div>;
  if (!loaded) return <p role="status">Loading first-run settings and backup destinations…</p>;
  const { state } = loaded;
  const { appPlan } = api;
  // Offered whenever the gateway can issue one: a kit needs no backup destination (D-028), because it also
  // brings the owner back in at the box.
  const kit = recoveryKit(api, state.kit);
  const previewPlan = appPlan ? async (id: string) => {
    const plan = await appPlan.call(api, id);
    if (plan.policy_verdict !== 'needs_approval' || typeof plan.plan?.summary !== 'string') throw new Error(plan.reason || 'the gateway refused this install');
    previewed.current.set(id, plan.plan_sha256);
    return plan.plan.summary;
  } : undefined;
  const landing = landingAfterSetup(0);
  // No mock backend: the demo gateway has no sites, so the place stays on the setup map only.
  const onSaveLocation = mock ? undefined : async (draft: OnboardingDraft): Promise<SavedPlace> => {
    const body = firstSite(draft);
    if (!body) throw new Error('Give the place a position first.');
    try {
      const saved = await viaSdk(() => sdk.call<GeoSite>({ method: 'POST', path: '/v1/sites', body }));
      return placeOf('saved', saved ?? body);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 409)) throw e;
      // A site with this ID is already on the box (a reload, a second browser): it is kept as it is, and
      // the owner is shown what is actually saved, not what was just typed.
      const sites = await viaSdk(() => sdk.call<GeoSite[]>({ method: 'GET', path: '/v1/sites' }));
      const existing = sites.find((s) => s.id === body.id);
      if (!existing) throw e;
      return placeOf('exists', existing);
    }
  };
  return (<>
    {recover && <WizardRecovery onBack={() => setRecover(false)} />}
    <div hidden={recover}>
    <Onboarding
      apps={apps}
      ownerConfigured
      onSaveLocation={onSaveLocation}
      finishLabel={landing === '/map' ? 'Open my map' : undefined}
      kit={kit}
      backupRecoveryAction={headless && state.destinations > 0 && state.kit.state !== 'confirmed' &&
        <button type="button" className="om-btn om-btn-secondary" onClick={() => setRecover(true)}>
          Set up a proven key for the backup kit
        </button>}
      previewPlan={previewPlan}
      initial={{ boxName: loaded.settings.box_name ?? '', ownerName: account?.display_name ?? '', timeZone: loaded.settings.time_zone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'UTC',
        backup: { destination: loaded.settings.backup_choice, destinationId: loaded.settings.backup_destination_id ?? undefined, kitSaved: false } }}
      localAddress={window.location.hostname.endsWith('.local') ? window.location.hostname : undefined}
      backupDestinations={loaded.destinations}
      onSaveSettings={async (draft) => {
        const body: FirstRunSettingsBody = { box_name: draft.boxName, time_zone: draft.timeZone,
          backup_choice: draft.backup.destination, backup_destination_id: draft.backup.destinationId ?? null };
        await api.saveOnboardingSettings(body);
        const saved = await api.onboardingSettings();
        if (!saved.saved || (Object.keys(body) as Array<keyof FirstRunSettingsBody>).some((key) => saved[key] !== body[key])) {
          throw new Error('Settings readback did not match. Try saving again.');
        }
      }}
      onThemeChange={(t) => applyTheme(t)}
      onFinish={async (_draft, requests) => {
          let sent = 0;
          for (const r of requests) {
            try {
              const shown = previewed.current.get(r.params.app_id);
              if (appPlan) {
                if (!shown) continue;
                // Bound to what the owner saw: a plan that changed since the preview is not filed.
                const now = await appPlan.call(api, r.params.app_id);
                if (now.plan_sha256 !== shown) continue;
                await hub.request(r.type, r.params.app_id, {}, now.plan_sha256);
              } else await hub.request(r.type, r.params.app_id);
              sent += 1;
            } catch {
              /* reported once below */
            }
          }
          if (requests.length) toast.show({ tone: sent === requests.length ? 'info' : 'warn', title: `${sent} of ${requests.length} install requests sent`, body: 'They wait in Approvals until you decide.' });
          landingRef.current = landingAfterSetup(requests.length);
      }}
      onLeave={() => {
        onDone();
        navigate(landingRef.current);
      }}
    />
    </div>
  </>);
}

function WizardRecovery({ onBack }: { onBack: () => void }) {
  const { token, signOut } = useSignedIn();
  const client = useGateway(token);
  return <main className="dash-page">
    <div className="dash-actions">
      <button type="button" onClick={onBack}>Back to setup</button>
      <button type="button" onClick={signOut}>Sign out</button>
    </div>
    <RecoverRemoteApprovals client={client} onRegistered={async () => onBack()} />
  </main>;
}

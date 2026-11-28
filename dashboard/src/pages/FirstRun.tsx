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
// Software settings persist through §12.41. Backup configuration stays in §12.12.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Onboarding, applyTheme, useToast, type StarterApp } from '@onemind/ui';
import type { CatalogApp } from '../api/types';
import type { BackupDestinationRecord, FirstRunSettings, FirstRunSettingsBody, FirstRunState } from '../api/client';
import { categorySlug, deployClass } from '../data/adapters';
import { useHub } from '../data/hub';
import { recoveryKit } from '../data/recoveryKit';
import { useGateway } from '../lib/gateway';
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

export function FirstRun({ onDone }: { onDone: () => void }) {
  const { api, account, anon } = useSignedIn();
  const hub = useHub();
  const toast = useToast();
  const navigate = useNavigate();
  const apps = useMemo(() => (hub.apps.data ?? []).map(toStarterApp).filter((a): a is StarterApp => !!a), [hub.apps.data]);
  const [loaded, setLoaded] = useState<{ settings: FirstRunSettings; destinations: BackupDestinationRecord[]; state: FirstRunState }>();
  const previewed = useRef(new Map<string, string>());
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
  return (<>
    {recover && <WizardRecovery onBack={() => setRecover(false)} />}
    <div hidden={recover}>
    <Onboarding
      apps={apps}
      ownerConfigured
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
          onDone();
          navigate(requests.length ? '/approvals' : '/');
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

// SPDX-License-Identifier: Apache-2.0
// The first-run wizard of @onemind/ui (Onboarding), wired. It opens once, right after the owner is
// created on the sign-in screen (setup flag in sessionStorage). Real effects only:
//  - "Create a passkey" runs the WebAuthn ceremony against /v1/auth/passkeys/register.
//  - Each starter app the owner ticks becomes an `app.install` REQUEST in Approvals. Nothing is
//    installed by the wizard (AI and automation never actuate; the owner approves each one).
// Software settings persist through §12.41. Backup configuration stays in §12.12.
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { Onboarding, applyTheme, useToast, type StarterApp } from '@onemind/ui';
import type { CatalogApp } from '../api/types';
import type { BackupDestinationRecord, FirstRunSettings, FirstRunSettingsBody } from '../api/client';
import { categorySlug, deployClass } from '../data/adapters';
import { useHub } from '../data/hub';
import { createPasskey, webauthnSupported } from '../lib/webauthn';
import { useSignedIn } from '../session';
import { WIZARD_KEY } from './SignIn';

export function toStarterApp(a: CatalogApp): StarterApp | undefined {
  const category = categorySlug(a.category);
  if (!category || a.installed || a.tier === 'blocked') return undefined;
  return { id: a.id, name: a.name || a.id, tagline: a.description ?? '', category, deployClass: deployClass(a.tier), minMemoryMb: 0 };
}

export const wizardPending = (): boolean => {
  try {
    return window.sessionStorage.getItem(WIZARD_KEY) === '1';
  } catch {
    return false;
  }
};
export const clearWizard = () => {
  try {
    window.sessionStorage.removeItem(WIZARD_KEY);
  } catch {
    /* nothing to clear */
  }
};

export function FirstRun({ onDone }: { onDone: () => void }) {
  const { api } = useSignedIn();
  const hub = useHub();
  const toast = useToast();
  const navigate = useNavigate();
  const apps = useMemo(() => (hub.apps.data ?? []).map(toStarterApp).filter((a): a is StarterApp => !!a), [hub.apps.data]);
  const [loaded, setLoaded] = useState<{ settings: FirstRunSettings; destinations: BackupDestinationRecord[] }>();
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setError(undefined);
    void Promise.all([api.onboardingSettings(), api.backupDestinations()]).then(([settings, destinations]) => {
      if (live) setLoaded({ settings, destinations });
    }).catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : 'Could not load settings.'); });
    return () => { live = false; };
  }, [api, attempt]);
  if (error) return <div role="alert">{error} <button onClick={() => setAttempt((x) => x + 1)}>Try again</button></div>;
  if (!loaded) return <p role="status">Loading first-run settings and backup destinations…</p>;
  return (
    <Onboarding
      apps={apps}
      initial={{ boxName: loaded.settings.box_name ?? '', timeZone: loaded.settings.time_zone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'UTC',
        backup: { destination: loaded.settings.backup_choice, destinationId: loaded.settings.backup_destination_id ?? undefined, kitSaved: false } }}
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
      onCreatePasskey={
        webauthnSupported()
          ? async () => {
              try {
                const o = await api.passkeyRegisterOptions();
                await api.passkeyRegister(await createPasskey(o.publicKey), 'First passkey');
                return true;
              } catch {
                return false;
              }
            }
          : undefined
      }
      onThemeChange={(t) => applyTheme(t)}
      onFinish={async (_draft, requests) => {
          let sent = 0;
          for (const r of requests) {
            try {
              await hub.request(r.type, r.params.app_id);
              sent += 1;
            } catch {
              /* reported once below */
            }
          }
          if (requests.length) toast.show({ tone: sent === requests.length ? 'info' : 'warn', title: `${sent} of ${requests.length} install requests sent`, body: 'They wait in Approvals until you decide.' });
          clearWizard();
          onDone();
          navigate(requests.length ? '/approvals' : '/');
      }}
    />
  );
}

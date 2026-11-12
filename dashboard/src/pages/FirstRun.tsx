// SPDX-License-Identifier: Apache-2.0
// The first-run wizard of @onemind/ui (Onboarding), wired. It opens once, right after the owner is
// created on the sign-in screen (setup flag in sessionStorage). Real effects only:
//  - "Create a passkey" runs the WebAuthn ceremony against /v1/auth/passkeys/register.
//  - Each starter app the owner ticks becomes an `app.install` REQUEST in Approvals. Nothing is
//    installed by the wizard (AI and automation never actuate; the owner approves each one).
// The box name, time zone and backup choice have no gateway route on main yet, so they are not
// saved; the wizard summary says so (see docs/dashboard/WIRING.md).
import { useMemo } from 'react';
import { useNavigate } from 'react-router';
import { Onboarding, applyTheme, useToast, type StarterApp } from '@onemind/ui';
import type { CatalogApp } from '../api/types';
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
  return (
    <Onboarding
      apps={apps}
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
      onFinish={(_draft, requests) => {
        void (async () => {
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
        })();
      }}
    />
  );
}

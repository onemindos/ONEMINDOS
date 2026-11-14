// SPDX-License-Identifier: Apache-2.0
// Secrets and owner override demo (#/secrets/<state>). Fixtures only; the demo never calls a
// gateway. Submitting really seals the form with WebCrypto to a key pair made in this tab, and
// shows the body that would be sent, so you can see no value leaves in plain text.
import { useEffect, useState } from 'react';
import { Card, OwnerOverrideDialog, OwnerOverrideMark, PageHeader, SecretsForm, approveBody, sealValues, type OwnerOverrideInfo, type SecretsPublicKey, type SecretsSubmission } from '../../../src';
import { b64u } from '../../../src/secrets/seal';
import './secrets-demo.css';
import { HERMES, OVERRIDE_MARK, VAULT, hermesSecrets, overrideMalware, overrideOff, overrideOn, overridePasskey, vaultBeforeInstall, vaultSecrets } from './fixtures';

export const SECRETS_STATES = ['install', 'required', 'change', 'error', 'override', 'override-off', 'override-blocked', 'override-passkey', 'override-agent', 'mark'] as const;
type State = (typeof SECRETS_STATES)[number];

async function demoKey(): Promise<SecretsPublicKey> {
  const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits'])) as CryptoKeyPair;
  const raw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return { alg: 'X25519', key: b64u(raw), key_id: 'sk_demo', sealed_alg: 'X25519-AES256GCM' };
}

const OVERRIDE: Partial<Record<State, OwnerOverrideInfo>> = {
  override: overrideOn,
  'override-off': overrideOff,
  'override-blocked': overrideMalware,
  'override-passkey': overridePasskey,
  'override-agent': overrideOn,
};

export function SecretsDemo({ arg }: { arg?: string }) {
  const state: State = (SECRETS_STATES as readonly string[]).includes(arg ?? '') ? (arg as State) : 'install';
  const [sent, setSent] = useState<string>();
  const [open, setOpen] = useState(true);
  useEffect(() => {
    setSent(undefined);
    setOpen(true);
  }, [state]);

  const send = async (appId: string, sub: SecretsSubmission) => {
    try {
      const sealed = Object.keys(sub.values).length ? await sealValues(await demoKey(), appId, sub.values) : undefined;
      const body = state === 'change' ? { ...(sealed ? { sealed } : {}), generate: sub.generate, clear: sub.clear } : approveBody({ sealed });
      setSent(JSON.stringify(body ?? {}, null, 2));
    } catch {
      setSent('This browser cannot seal with X25519 (WebCrypto). The dashboard falls back to the terminal: onemind-secrets.');
    }
  };

  const override = OVERRIDE[state];
  return (
    <>
      <PageHeader title="Secrets and owner override" lede="What the owner sees when an app needs keys, and when an install failed its scan." />
      <nav className="sec-demo-states" aria-label="Demo state">
        <span className="d-demo-flag">Demo state</span>
        {SECRETS_STATES.map((st) => (
          <a key={st} href={`#/secrets/${st}`} aria-current={st === state ? 'page' : undefined}>
            {st}
          </a>
        ))}
      </nav>
      <Card>
        {state === 'install' && <SecretsForm app={HERMES} secrets={hermesSecrets} mode="install" onSubmit={(s) => void send(HERMES.id, s)} onCancel={() => setSent(undefined)} />}
        {state === 'required' && <SecretsForm app={VAULT} secrets={vaultBeforeInstall} mode="install" onSubmit={(s) => void send(VAULT.id, s)} />}
        {state === 'change' && <SecretsForm app={VAULT} secrets={vaultSecrets} mode="change" onSubmit={(s) => void send(VAULT.id, s)} />}
        {state === 'error' && (
          <SecretsForm
            app={VAULT}
            secrets={vaultBeforeInstall}
            mode="install"
            error="stale_precondition: enter the required secrets before approving: vault-like-credentials/PROVIDER_API_KEY"
            onSubmit={(s) => void send(VAULT.id, s)}
          />
        )}
        {state === 'mark' && (
          <p>
            Hermes Agent installed · <OwnerOverrideMark mark={OVERRIDE_MARK} />
          </p>
        )}
        {override && (
          <>
            <p>The approval card offers “Override the scan” here; the dialog says what the box allows.</p>
            <OwnerOverrideDialog
              open={open}
              app={HERMES}
              info={override}
              requestedBy={state === 'override-agent' ? { id: 'agent:hermes-agent', kind: 'agent' } : { id: 'owner', kind: 'person' }}
              onClose={() => setOpen(false)}
              onConfirm={(input) => {
                setSent(JSON.stringify(approveBody({ override: input }), null, 2));
                setOpen(false);
              }}
            />
          </>
        )}
      </Card>
      {sent && (
        <Card>
          <h2 className="om-subhead">Body the dashboard would send</h2>
          <pre className="sec-demo-body">{sent}</pre>
        </Card>
      )}
    </>
  );
}

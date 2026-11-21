// SPDX-License-Identifier: Apache-2.0
// Control Hub, Secrets tab (CORE-SECRETS-1, #206): write-only app secrets. The hub says which
// keys an app declares and whether each is set, never a value. A typed value is sealed in this
// browser to the box key (GET /v1/secrets/public-key) before it is sent, and the send only FILES
// an `app.configure` request: nothing changes until an owner approves it in Approvals.
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { SecretsForm, sealValues, useToast, type SealedInput, type SecretsSubmission } from '@onemind/ui';
import { REQUEST_TTL_MS, errorText } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { uuidv4 } from '../lib/uuid';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

const NO_X25519 = 'This browser cannot seal secrets (it lacks X25519 in WebCrypto). Use the onemind-secrets helper in a terminal; nothing was sent.';

export function SecretsPanel({ app }: { app: { id: string; name: string } }) {
  const { api, canDecide } = useSignedIn();
  const toast = useToast();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const secrets = usePoll(async () => {
    if (!api.appSecrets) throw new Error('Secrets cannot be read by this gateway client.');
    return api.appSecrets(app.id);
  }, 0);

  const submit = async (sub: SecretsSubmission) => {
    if (!api.requestSecretsChange || !api.secretsPublicKey) { setError('This gateway client cannot file secret changes.'); return; }
    setBusy(true);
    setError(undefined);
    try {
      let sealed: SealedInput | undefined;
      if (Object.keys(sub.values).length > 0) {
        const pk = await api.secretsPublicKey();
        try { sealed = await sealValues(pk, app.id, sub.values); } catch { throw new Error(NO_X25519); }
      }
      const key = { idempotency_key: uuidv4(), expires_at: new Date(Date.now() + (api.hubOffsetMs() ?? 0) + REQUEST_TTL_MS).toISOString() };
      const action = await api.requestSecretsChange(app.id, { ...(sealed ? { sealed } : {}), generate: sub.generate, clear: sub.clear }, key);
      toast.show({ tone: 'info', title: 'Request sent', body: 'The values are sealed. Nothing changes until the owner approves it in Approvals.' });
      void secrets.reload();
      navigate(href.approval(action.id));
    } catch (e) {
      const msg = errorText(e).message;
      setError(msg);
      toast.show({ tone: 'bad', title: 'Could not request the secret change', body: msg });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Load res={secrets} what="Loading secrets">
      {(s) =>
        s.secrets.length === 0 ? (
          <p className="om-hint">{app.name} declares no secrets.</p>
        ) : canDecide === 'no' ? (
          <p className="om-note om-tone-warn" role="note">Only an owner can change secrets. This account is not an owner, so the form is hidden.</p>
        ) : (
          <SecretsForm app={app} secrets={s} mode="change" submitLabel="Request change" busy={busy} error={error} onSubmit={(sub) => void submit(sub)} />
        )
      }
    </Load>
  );
}

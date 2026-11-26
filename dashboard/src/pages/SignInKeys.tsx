// SPDX-License-Identifier: Apache-2.0
// Settings > Security > Sign-in keys (D-028; gateway permissions design 3.11, PR 17).
// Each key shows the level it proves: L1 Device check (any passkey, synced ones included) or L2 Proven key
// (a device-bound key whose make and model OneMind could prove). Destructive and physical approvals and
// security settings ask for L2 by default. Adding a key runs the browser's WebAuthn ceremony; once you
// hold a proven key, adding another needs that key first (a step-up bound to this one change).
// Removing a key or a trusted model only takes power away, so it happens at once (audited).
// Trusting a new key model is an owner action: it waits in Approvals for a proven key.
// Editing the verification table itself is Settings > Permissions (design PR 16); the API and
// `onemind permissions verify` already have it.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, Table, VerificationBadge, type VerificationLevel } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { createPasskey, getPasskey, webauthnSupported } from '../lib/webauthn';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Load } from './parts';

type Key = components['schemas']['Passkey'];
type Registered = components['schemas']['PasskeyRegistered'];
type Model = components['schemas']['TrustedModel'];
type Table_ = components['schemas']['VerificationTable'];
type StepUpOptions = components['schemas']['StepUpOptions'];
type StepUpGrant = components['schemas']['StepUpGrant'];
type Json = Record<string, unknown>;

const UV_METHODS = [
  ['fingerprint_internal', 'Fingerprint reader on the key'],
  ['faceprint_internal', 'Face check on the key'],
  ['passcode_internal', 'PIN on the key'],
] as const;
const strong = (k: { level: string }) => k.level === 'L2' || k.level === 'L3';

function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : e.status === 409 ? 'conflict' : 'unknown', e.message, e.reason) : e;
}
async function call<T>(client: OneMind, method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  try { return await client.call<T>({ method, path, body, ...(headers ? { headers } : {}) }); } catch (e) { throw apiError(e); }
}
const ago = (iso: string | null | undefined, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : 'Never');

/** A change that needs L2: sign a challenge for exactly this change, get a single-use grant. */
async function stepUp(client: OneMind, op: string, body: Json = {}, target = ''): Promise<string> {
  const o = await call<StepUpOptions>(client, 'POST', '/v1/auth/step-up/options', { op, target, body });
  const credential = await getPasskey(o.publicKey);
  return (await call<StepUpGrant>(client, 'POST', '/v1/auth/step-up', { credential })).step_up;
}

export function SignInKeys() {
  const { token, mock, principal } = useSignedIn();
  if (mock) return <><PageHeader title="Sign-in keys" /><Card title="Sign-in keys"><p role="status">Connect to a real hub to manage sign-in keys. Demo mode has none.</p></Card></>;
  return <LiveSignInKeys token={token} owner={principal?.role === 'owner'} />;
}

function LiveSignInKeys({ token, owner }: { token: string; owner: boolean }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const keys = usePoll(() => call<Key[]>(client, 'GET', '/v1/auth/passkeys'), 0);
  const table = usePoll(() => (owner ? call<Table_>(client, 'GET', '/v1/verification-requirements') : Promise.resolve(undefined)), 0);
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string }>();
  const [confirming, setConfirming] = useState<string>();
  const now = client.hubNow();

  const run = async (job: () => Promise<void>, what: string) => {
    setBusy(true); setNote(undefined);
    try { await job(); } catch (e) {
      const text = e instanceof ApiError && e.reason === 'verification_level_unmet' ? 'this needs your proven key, and none of your keys is one yet'
        : e instanceof ApiError && e.reason === 'step_up_required' ? 'this needs a fresh passkey check; try again and use your key when asked'
          : e instanceof Error ? e.message : String(e);
      setNote({ tone: 'bad', text: `${what}: ${text}` });
    } finally { setBusy(false); void keys.reload(); void table.reload(); }
  };

  const addKey = () => run(async () => {
    let options: { publicKey: Json };
    try {
      options = await call(client, 'POST', '/v1/auth/passkeys/register/options', {});
    } catch (e) {
      if (!(e instanceof ApiError && e.reason === 'step_up_required')) throw e;
      // You hold a proven key: it vouches for the new one (a new device can't vouch for itself).
      const grant = await stepUp(client, 'auth.passkeys.register');
      options = await call(client, 'POST', '/v1/auth/passkeys/register/options', {}, { 'OneMind-Step-Up': grant });
    }
    const credential = await createPasskey(options.publicKey);
    const r = await call<Registered>(client, 'POST', '/v1/auth/passkeys/register', { credential, label: label.trim() || 'Security key' });
    setLabel('');
    setNote({ tone: strong(r) ? 'ok' : 'warn', text: `${r.label} added at ${r.level}. ${r.explanation}` });
  }, 'Adding the key');

  const remove = (k: Key) => run(async () => {
    await call<void>(client, 'DELETE', `/v1/auth/passkeys/${encodeURIComponent(k.credential_id)}`);
    setConfirming(undefined);
  }, `Removing ${k.label}`);

  return <div className="dash-stack">
    <PageHeader title="Sign-in keys" lede="Your passkeys and security keys, and how strongly each one can check it's you. OneMind never sees your face, fingerprint or PIN: your device checks you and only tells OneMind that it did." />
    <Load res={keys} what="Loading your keys">
      {(list) => <>
        <TwoKeyNudge list={list} grace={table.data?.grace} />
        <Card title="Your keys" aside={webauthnSupported() ? undefined : <span className="om-hint">This browser can't add passkeys.</span>}>
          {list.length === 0 ? <p className="om-hint">No keys yet. Add one below.</p> : <Table
            caption="Your keys" hideCaption rows={list} rowKey={(k) => k.credential_id}
            columns={[
              { key: 'label', header: 'Name', render: (k) => <><strong>{k.label}</strong>{!strong(k) && k.explanation && <p className="om-hint">{k.explanation}</p>}</> },
              { key: 'level', header: 'Level', render: (k) => <VerificationBadge level={k.level as VerificationLevel} /> },
              { key: 'model', header: 'Model', render: (k) => k.model ?? '—', secondary: true },
              { key: 'kind', header: 'Kind', render: (k) => (k.device_bound === true ? 'Stays on this device' : k.device_bound === false ? 'Synced between devices' : 'Unknown'), secondary: true },
              { key: 'added', header: 'Added', render: (k) => ago(k.created_at, now), secondary: true },
              { key: 'used', header: 'Last used', render: (k) => ago(k.last_used_at, now), secondary: true },
              { key: 'x', header: 'Actions', render: (k) => confirming === k.credential_id
                ? <Button size="sm" variant="danger" disabled={busy} aria-label={`Confirm remove ${k.label}`} onClick={() => void remove(k)}>Confirm remove</Button>
                : <Button size="sm" variant="ghost" disabled={busy} aria-label={`Remove ${k.label}`} onClick={() => setConfirming(k.credential_id)}>Remove</Button> },
            ]}
          />}
          {webauthnSupported() && <div className="dash-actions">
            <label>Name for the new key{' '}<input value={label} maxLength={100} onChange={(e) => setLabel(e.target.value)} placeholder="Security key" /></label>
            <Button icon="plus" disabled={busy} onClick={() => void addKey()}>Add a key</Button>
          </div>}
          {note && <p role="status" className={`om-note om-tone-${note.tone}`}>{note.text}</p>}
        </Card>
      </>}
    </Load>
    {owner && <TrustedModels client={client} onError={(text) => setNote({ tone: 'bad', text })} />}
  </div>;
}

function TwoKeyNudge({ list, grace }: { list: Key[]; grace?: boolean }) {
  const proven = list.filter(strong).length;
  if (proven >= 2) return null;
  return <Card title={proven === 1 ? 'Add a second proven key' : 'Add two proven keys'} variant="attention">
    <p>
      {proven === 1
        ? 'You have one proven key. Add a second one (a spare security key, or the OneMind app key) so losing one never locks you out of high-risk approvals.'
        : 'Restoring over live data, removing a machine, physical actions and security settings ask for a proven key. Add two, so losing one is never a lock-out.'}
    </p>
    {grace && <p className="om-hint"><StatusPill tone="warn" label="Until then" /> Those approvals accept a Device check key, so your box keeps working. Physical actions never do.</p>}
    <p className="om-hint">Your files never depend on a proven key: signing in, downloading and restoring into a new folder need only a normal sign-in.</p>
  </Card>;
}

function TrustedModels({ client, onError }: { client: OneMind; onError: (text: string) => void }) {
  const models = usePoll(() => call<Model[]>(client, 'GET', '/v1/auth/authenticator-allowlist'), 0);
  const [form, setForm] = useState({ aaguid: '', name: '', root: '', uv: ['fingerprint_internal'] as string[] });
  const [filed, setFiled] = useState<string>();
  const [busy, setBusy] = useState(false);
  const ready = form.aaguid.trim() && form.name.trim() && form.root.includes('BEGIN CERTIFICATE') && form.uv.length > 0;

  const request = async () => {
    setBusy(true); setFiled(undefined);
    try {
      const a = await call<{ id: string }>(client, 'POST', '/v1/actions', {
        type: 'authenticator.allowlist.add',
        params: { aaguid: form.aaguid.trim(), name: form.name.trim(), roots: [form.root.trim()], user_verification: form.uv },
        idempotency_key: `dash-model-${Date.now().toString(36)}`,
        expires_at: new Date(client.hubNow() + 24 * 3600_000).toISOString(),
      });
      setFiled(a.id);
      setForm({ aaguid: '', name: '', root: '', uv: ['fingerprint_internal'] });
    } catch (e) { onError(`Asking to trust ${form.name || 'the model'}: ${e instanceof Error ? e.message : String(e)}`); } finally { setBusy(false); }
  };
  const untrust = async (m: Model) => {
    try { await call<void>(client, 'DELETE', `/v1/auth/authenticator-allowlist/${encodeURIComponent(m.aaguid)}`); } catch (e) { onError(`Removing ${m.name}: ${e instanceof Error ? e.message : String(e)}`); }
    void models.reload();
  };

  return <Card title="Trusted key models" subtitle="Security keys whose make and model OneMind can prove. A key of one of these models, that can check a fingerprint or face and stays on its device, is a proven key.">
    <Load res={models} what="Loading trusted models">
      {(list) => list.length === 0 ? <p className="om-hint">No trusted models yet, so every key works at Device check.</p> : <Table
        caption="Trusted key models" hideCaption rows={list} rowKey={(m) => m.aaguid}
        columns={[
          { key: 'name', header: 'Model', render: (m) => m.name },
          { key: 'bio', header: 'Can check a fingerprint or face', render: (m) => (m.biometric ? 'Yes' : 'No') },
          { key: 'from', header: 'From', render: (m) => (m.source === 'shipped' ? 'Comes with the OS' : 'Added by an owner'), secondary: true },
          { key: 'x', header: 'Actions', render: (m) => (m.source === 'owner' ? <Button size="sm" variant="ghost" aria-label={`Stop trusting ${m.name}`} onClick={() => void untrust(m)}>Stop trusting</Button> : null) },
        ]}
      />}
    </Load>
    <details className="om-details">
      <summary>Trust another model</summary>
      <p className="om-hint">Take these from the FIDO Metadata Service entry for the key. The request waits in Approvals until an owner approves it with a proven key.</p>
      <label>Model id (AAGUID){' '}<input value={form.aaguid} onChange={(e) => setForm({ ...form, aaguid: e.target.value })} /></label>
      <label>Model name{' '}<input value={form.name} maxLength={100} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label>Attestation root certificate (PEM){' '}<textarea rows={4} value={form.root} onChange={(e) => setForm({ ...form, root: e.target.value })} /></label>
      <fieldset><legend>How the key checks the person</legend>
        {UV_METHODS.map(([id, text]) => <label key={id}><input type="checkbox" checked={form.uv.includes(id)} onChange={(e) => setForm({ ...form, uv: e.target.checked ? [...form.uv, id] : form.uv.filter((u) => u !== id) })} /> {text}</label>)}
      </fieldset>
      <Button disabled={!ready || busy} onClick={() => void request()}>Ask to trust this model</Button>
      {filed && <p role="status" className="om-note om-tone-ok">Requested. Approve it in Approvals with your proven key (request {filed}).</p>}
    </details>
  </Card>;
}

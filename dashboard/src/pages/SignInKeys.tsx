// SPDX-License-Identifier: Apache-2.0
// Settings > Security > Sign-in keys (D-028; gateway permissions design 3.11, PR 17).
// Each key shows the level it proves: L1 Device check (any passkey, synced ones included) or L2 Proven key
// (a device-bound key whose make and model OneMind could prove). Destructive and physical approvals and
// security settings ask for L2 by default. Adding a key runs the browser's WebAuthn ceremony; once you
// hold a proven key, adding another needs that key first (a step-up bound to this one change, made in place
// by the SDK's shared helper: the hub's 401 names it, the browser asks for the key, the request goes again).
// Removing a key or a trusted model only takes power away: removing a key asks for a fresh passkey check, a
// trusted model goes at once (both audited). Removing your last proven key (or the model behind it) is
// warned about first and needs that key, or confirming at the box when it is lost: afterwards high-risk
// approvals wait for a recovery path, they never go back to a Device check key (the grace is one-way).
// Before your box's first proven key (N-1 b), high-risk changes are confirmed at the box: a passkey plus the
// code its own screen shows (lib/boxcode.tsx), and the first proven key is added there too.
// Trusting a new key model is an owner action: it waits in Approvals for a proven key.
// Editing the verification table itself is Settings > Verification levels (VerificationLevels.tsx, design
// PR 16), also `onemind permissions verify`.
import { useState } from 'react';
import { completeStepUp, OneMind, OneMindError, STEP_UP_HEADER, type components } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, Table, VerificationBadge, type VerificationLevel } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useGateway } from '../lib/gateway';
import { createPasskey, getPasskey, webauthnSupported } from '../lib/webauthn';
import { askBoxCode } from '../lib/boxcode';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { Load } from './parts';

type Key = components['schemas']['Passkey'];
type Registered = components['schemas']['PasskeyRegistered'];
type Model = components['schemas']['TrustedModel'];
type Table_ = components['schemas']['VerificationTable'];
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
  try { return await client.call<T>({ method, path, body, headers }); } catch (e) { throw apiError(e); }
}
const ago = (iso: string | null | undefined, now: number) => (iso ? formatAgo(secondsSince(iso, now)) : 'Never');

/** Plain words for why adding or removing a key did not happen. */
export function keyErrorText(e: unknown): string {
  if (e instanceof ApiError && e.reason === 'verification_level_unmet') return 'this needs your proven key, and none of your keys is one yet';
  if (e instanceof ApiError && e.reason === 'box_code_required') return 'the code from the box\'s own screen was missing or wrong, so nothing changed. Ask again: the box shows a new code each time';
  if (e instanceof ApiError && e.reason === 'box_code_locked') return 'too many wrong codes from the box\'s screen; wait 15 minutes, then try again';
  if (e instanceof ApiError && e.reason === 'box_presence_unavailable') return 'this box has no screen to show a confirmation code, so this waits for a proven key';
  if (e instanceof ApiError && e.reason === 'cancelled') return 'cancelled, so nothing changed';
  // The hub named no step-up the page could make in place (an older hub), or the check did not finish.
  if (e instanceof ApiError && e.reason === 'step_up_required') return 'the hub wants a fresh passkey check that this page could not make. Sign out, sign in again with your passkey, then do this again';
  if (e instanceof Error && e.name === 'NotAllowedError') return 'the passkey check was cancelled or timed out, so nothing changed';
  return e instanceof Error ? e.message : String(e);
}

export function SignInKeys() {
  const { token, mock } = useSignedIn();
  // A real gateway session carries no role; the shell asks GET /v1/me for it (as SettingsSecurity does). Refs #1284.
  const { role } = useShell();
  if (mock) return <><PageHeader title="Sign-in keys" /><Card title="Sign-in keys"><p role="status">Connect to a real hub to manage sign-in keys. Demo mode has none.</p></Card></>;
  // The key remounts when the role arrives, so the owner's verification table is fetched then, not skipped (GET /v1/me can answer after mount).
  const owner = role === 'owner';
  return <LiveSignInKeys key={owner ? 'owner' : 'other'} token={token} owner={owner} />;
}

function LiveSignInKeys({ token, owner }: { token: string; owner: boolean }) {
  const client = useGateway(token); // with the passkey signer: a step-up the hub names is made in place
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
      setNote({ tone: 'bad', text: `${what}: ${keyErrorText(e)}` });
    } finally { setBusy(false); void keys.reload(); void table.reload(); }
  };

  const addKey = () => run(async () => {
    // Once you hold a proven key it vouches for the new one first (a new device can't vouch for itself):
    // the hub names that step-up and the client makes it before the options come back.
    const name = label.trim() || 'Security key';
    const register = async (atBox: boolean) => {
      const options = await call<{ publicKey: Json; box_code_if_proven?: boolean }>(client, 'POST', '/v1/auth/passkeys/register/options', {});
      // N-1 b: the box's first proven key is added at the box. Asked only after the key turned out to be one.
      const box_code = atBox && options.box_code_if_proven ? await askBoxCode('add a proven key') : undefined;
      const credential = await createPasskey(options.publicKey);
      return call<Registered>(client, 'POST', '/v1/auth/passkeys/register', { credential, label: name, ...(box_code ? { box_code } : {}) });
    };
    let r: Registered;
    try { r = await register(false); } catch (e) {
      if (!(e instanceof ApiError && e.reason === 'box_code_required')) throw e;
      setNote({ tone: 'warn', text: `${name} is a proven key. Your box's first proven key is added at the box: type the code its screen shows, then use the key once more.` });
      r = await register(true);
    }
    setLabel('');
    setNote({ tone: strong(r) ? 'ok' : 'warn', text: `${r.label} added at ${r.level}. ${r.explanation}` });
  }, 'Adding the key');

  const remove = (k: Key) => run(async () => {
    await call<void>(client, 'DELETE', `/v1/auth/passkeys/${encodeURIComponent(k.credential_id)}`);
    setConfirming(undefined);
  }, `Removing ${k.label}`);
  // A lost or stolen last proven key can't confirm its own removal: an owner at the box confirms instead,
  // with any passkey plus the code the box's screen shows (design 3.11: a lost key can always be stopped).
  const removeAtBox = (k: Key) => run(async () => {
    const grant = await completeStepUp(client, { op: 'auth.passkeys.delete', target: k.credential_id, body: {}, required_level: 'L2', box: 'alt' },
      getPasskey, { atBox: true, boxCode: askBoxCode }).catch((e: unknown) => { throw apiError(e); });
    await call<void>(client, 'DELETE', `/v1/auth/passkeys/${encodeURIComponent(k.credential_id)}`, undefined, { [STEP_UP_HEADER]: grant });
    setConfirming(undefined);
  }, `Removing ${k.label}`);

  return <div className="dash-stack">
    <PageHeader title="Sign-in keys" lede="Your passkeys and security keys, and how strongly each one can check it's you. OneMind never sees your face, fingerprint or PIN: your device checks you and only tells OneMind that it did." />
    <Load res={keys} what="Loading your keys">
      {(list) => <>
        <TwoKeyNudge list={list} grace={table.data?.grace} recovery={table.data?.recovery_needed} />
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
                ? <>
                    {strong(k) && list.filter(strong).length === 1 && <p role="alert" className="om-note om-tone-warn">{LAST_PROVEN_WARNING}</p>}
                    <Button size="sm" variant="danger" disabled={busy} aria-label={`Confirm remove ${k.label}`} onClick={() => void remove(k)}>Confirm remove</Button>
                    {strong(k) && list.filter(strong).length === 1 && <>{' '}<Button size="sm" variant="ghost" disabled={busy} aria-label={`Lost ${k.label}: confirm at the box`} onClick={() => void removeAtBox(k)}>Lost it? Confirm at the box</Button></>}
                    {' '}<Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming(undefined)}>Keep it</Button>
                  </>
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
    {owner && <TrustedModels client={client} keys={keys.data ?? []} onError={(text) => setNote({ tone: 'bad', text })} />}
  </div>;
}

/** Design 3.11: removing the last proven key is warned about before it happens. The grace is one-way, so
 *  nothing falls back to a Device check key afterwards. */
export const LAST_PROVEN_WARNING = 'This is your last proven key. High-risk approvals will need a recovery path until you add another strong key: restores over live data, removing a machine, physical actions and security settings wait, and never go back to accepting a Device check key. Your files stay reachable with a normal sign-in. Add a spare first if you can.';

function TwoKeyNudge({ list, grace, recovery }: { list: Key[]; grace?: boolean; recovery?: boolean }) {
  const proven = list.filter(strong).length;
  if (proven >= 2) return null;
  return <Card title={proven === 1 ? 'Add a second proven key' : 'Add two proven keys'} variant="attention">
    <p>
      {proven === 1
        ? 'You have one proven key. Add a second one (a spare security key of a trusted model) so losing one never locks you out of high-risk approvals.'
        : 'Restoring over live data, removing a machine, physical actions and security settings ask for a proven key. Add two, so losing one is never a lock-out.'}
    </p>
    {grace && proven === 0 && <p className="om-hint"><StatusPill tone="warn" label="Until then" /> Those approvals accept a Device check key plus the code on the box's own screen, so you confirm them standing at the box. Physical actions never do.</p>}
    {recovery && proven === 0 && <p className="om-hint"><StatusPill tone="bad" label="Waiting" /> Your box had a proven key and has none now, so those approvals wait until you add one. Add it here while standing at the box: it asks for the code on the box's screen.</p>}
    <p className="om-hint">Your files never depend on a proven key: signing in, downloading and restoring into a new folder need only a normal sign-in.</p>
  </Card>;
}

function TrustedModels({ client, keys, onError }: { client: OneMind; keys: Key[]; onError: (text: string) => void }) {
  const models = usePoll(() => call<Model[]>(client, 'GET', '/v1/auth/authenticator-allowlist'), 0);
  const [form, setForm] = useState({ aaguid: '', name: '', root: '', uv: ['fingerprint_internal'] as string[] });
  const [filed, setFiled] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [dropping, setDropping] = useState<string>();
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
    // The model behind your last proven key asks for that key in place (the hub names the step-up).
    try { await call<void>(client, 'DELETE', `/v1/auth/authenticator-allowlist/${encodeURIComponent(m.aaguid)}`); } catch (e) { onError(`Removing ${m.name}: ${keyErrorText(e)}`); }
    setDropping(undefined);
    void models.reload();
  };
  const dropsTo = (m: Model) => keys.filter((k) => strong(k) && k.aaguid === m.aaguid).map((k) => k.label);

  return <Card title="Trusted key models" subtitle="Security keys whose make and model OneMind can prove. A key of one of these models, that can check a fingerprint or face and stays on its device, is a proven key.">
    <Load res={models} what="Loading trusted models">
      {(list) => list.length === 0 ? <p className="om-hint">No trusted models yet, so every key works at Device check.</p> : <Table
        caption="Trusted key models" hideCaption rows={list} rowKey={(m) => m.aaguid}
        columns={[
          { key: 'name', header: 'Model', render: (m) => m.name },
          { key: 'bio', header: 'Can check a fingerprint or face', render: (m) => (m.biometric ? 'Yes' : 'No') },
          { key: 'from', header: 'From', render: (m) => (m.source === 'shipped' ? 'Comes with the OS' : 'Added by an owner'), secondary: true },
          { key: 'x', header: 'Actions', render: (m) => (m.source !== 'owner' ? null : dropping === m.aaguid
            ? <>
                <p role="alert" className="om-note om-tone-warn">{dropsTo(m).length ? `These keys drop to Device check at once: ${dropsTo(m).join(', ')}.` : 'None of your keys is of this model.'}</p>
                <Button size="sm" variant="danger" aria-label={`Confirm stop trusting ${m.name}`} onClick={() => void untrust(m)}>Stop trusting</Button>
                {' '}<Button size="sm" variant="ghost" onClick={() => setDropping(undefined)}>Keep it</Button>
              </>
            : <Button size="sm" variant="ghost" aria-label={`Stop trusting ${m.name}`} onClick={() => setDropping(m.aaguid)}>Stop trusting</Button>) },
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

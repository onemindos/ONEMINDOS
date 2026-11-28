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
import type { PasskeyRegisterOptions } from '../api/wiring';
import { keyErrorText } from '../lib/keyErrors';
import { usePoll } from '../lib/hooks';
import { useGateway } from '../lib/gateway';
import { registerPasskey } from '../lib/registerPasskey';
import { createPasskey, getPasskey, webauthnSupported } from '../lib/webauthn';
import { askBoxCode } from '../lib/boxcode';
import { askVerification } from '../lib/verification';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { Load, TextField, useBusy } from './parts';
import { RecoveryKit } from './RecoveryKit';

type Key = components['schemas']['Passkey'];
type Registered = components['schemas']['PasskeyRegistered'];
type Model = components['schemas']['TrustedModel'];
type Table_ = components['schemas']['VerificationTable'];

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
    const r = await registerPasskey({
      passkeyRegisterOptions: () => call<PasskeyRegisterOptions>(client, 'POST', '/v1/auth/passkeys/register/options', {}),
      passkeyRegister: (credential, label, box_code) => call<Registered>(client, 'POST', '/v1/auth/passkeys/register',
        { credential, label, box_code } satisfies components['schemas']['PasskeyRegisterBody']),
    }, name, () => {
      setNote({ tone: 'warn', text: `${name} is a proven key. Your box's first proven key is added at the box: type the code its screen shows, then use the key once more.` });
    });
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
      getPasskey, { atBox: true, boxCode: askBoxCode,
        verification: async (request) => ({ ...await askVerification({ ...request, box: 'required' }), atBox: true }),
      }).catch((e: unknown) => { throw apiError(e); });
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
    {owner && <>
      <RecoverRemoteApprovals client={client} onRegistered={keys.reload} />
      <TrustedModels client={client} keys={keys.data ?? []} onError={(text) => setNote({ tone: 'bad', text })} />
    </>}
  </div>;
}

export function RecoverRemoteApprovals({ client, onRegistered }: { client: OneMind; onRegistered: () => Promise<void> }) {
  const path = '/v1/auth/recovery/remote';
  const status = usePoll(() => call<components['schemas']['RemoteRecoveryStatus']>(client, 'GET', path), 30_000);
  const [kitCode, setKitCode] = useState('');
  const [upgradeKit, setUpgradeKit] = useState<components['schemas']['SetupKit']>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, run] = useBusy();
  const attempt = (job: () => Promise<unknown>) => void run(async () => {
    setError(undefined);
    setNotice(undefined);
    try { await job(); await status.reload(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  });
  if (!status.data) return null;
  return <Card title="Recover remote approvals">
    <p className="om-hint">If you lose a proven key, start recovery with your kit code and a fresh sign-in using an authenticator or passkey. After 72 hours, you can register a replacement proven key.</p>
    {upgradeKit ? <RecoveryKit kit={upgradeKit} busy={busy} onSaved={() => {
      setKitCode(upgradeKit.recovery_code);
      setUpgradeKit(undefined);
    }} /> : status.data.upgrade_kit_available ? <>
      <p className="om-hint">This account was created before recovery kits. Sign in with an authenticator or passkey on your home network to get its recovery code.</p>
      <Button disabled={busy} onClick={() => attempt(async () => {
        setUpgradeKit(await call<components['schemas']['SetupKit']>(client, 'POST', '/v1/auth/setup/kit?legacy_upgrade=true'));
      })}>Get the account recovery kit</Button>
    </> : status.data.state === 'none' ? <form className="dash-form" onSubmit={(e) => {
      e.preventDefault();
      if (busy || !kitCode.trim()) return;
      attempt(async () => {
        await call<components['schemas']['RemoteRecoveryStatus']>(client, 'POST', path,
          { recovery_code: kitCode.trim() } satisfies components['schemas']['RemoteRecoveryBody']);
        setKitCode('');
      });
    }}>
      <TextField id="remote-recovery-code" label="Recovery kit code" type="password" value={kitCode} onChange={setKitCode} />
      <Button type="submit" disabled={busy || !kitCode.trim()}>Start the 72-hour wait</Button>
    </form> : <>
      <p role="status">{status.data.state === 'waiting'
        ? `You can register a replacement key after ${status.data.available_at ? new Date(status.data.available_at).toLocaleString() : 'the waiting period'}.`
        : `Your recovery request is ready${status.data.expires_at ? ` until ${new Date(status.data.expires_at).toLocaleString()}` : ''}.`}</p>
      {status.data.state === 'ready' && <p className="om-hint">Use a device-bound security key from a model trusted by this box.</p>}
      <div className="dash-identity-actions">
        {status.data.state === 'ready' && webauthnSupported() && <Button variant="primary" disabled={busy} onClick={() => attempt(async () => {
          const options = await call<PasskeyRegisterOptions>(client, 'POST', '/v1/auth/passkeys/register/options?remote_recovery=true', {});
          const key = await call<Registered>(client, 'POST', '/v1/auth/passkeys/register', { credential: await createPasskey(options.publicKey), label: 'Recovery key' });
          await onRegistered();
          setNotice(`${key.label} added at ${key.level}.`);
        })}>Add a replacement proven key</Button>}
        <Button variant="ghost" disabled={busy} onClick={() => attempt(() => call<void>(client, 'DELETE', path))}>Cancel recovery</Button>
      </div>
    </>}
    {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
    {notice && <p role="status" className="om-note om-tone-ok">{notice}</p>}
  </Card>;
}

/** Design 3.11: removing the last proven key is warned about before it happens. The grace is one-way, so
 *  nothing falls back to a Device check key afterwards. */
export const LAST_PROVEN_WARNING = 'This is your last proven key. Remote high-risk approvals will need a recovery path until you add another strong key. Some local changes can use a fresh sign-in check plus the box’s screen code. Physical actions never go back to accepting a Device check key. Your files stay reachable with a normal sign-in.';

function TwoKeyNudge({ list, grace, recovery }: { list: Key[]; grace?: boolean; recovery?: boolean }) {
  const proven = list.filter(strong).length;
  if (proven >= 2) return null;
  return <Card title={proven === 1 ? 'Add a second proven key' : 'Add two proven keys'} variant="attention">
    <p>
      {proven === 1
        ? 'You have one proven key. Add a second one (a spare security key of a trusted model) so losing one never locks you out of high-risk approvals.'
        : 'Restoring over live data, removing a machine, physical actions and security settings ask for a proven key. Add two, so losing one is never a lock-out.'}
    </p>
    {grace && proven === 0 && <p className="om-hint"><StatusPill tone="warn" label="At the box" /> Eligible approvals accept a Device check key plus the code on the box's own screen. A fresh password and authenticator code can also verify you before you enter the screen code.</p>}
    {recovery && proven === 0 && <p className="om-hint"><StatusPill tone="bad" label="Replacement needed" /> Your box had a proven key and has none now. Remote high-risk approvals need a replacement. Use recovery below or add a key while standing at the box.</p>}
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

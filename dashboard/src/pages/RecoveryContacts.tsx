// SPDX-License-Identifier: Apache-2.0
// Settings > Account: recovery contacts (gateway permissions design 25d, D-028). An owner invites up
// to 5 people who can later confirm a recovery. They never see your data or approve anything. Adding
// one, or shortening the cooling-off, needs a fresh passkey sign-in; removing one does not. A household
// adult sees the invitations addressed to them and accepts in the OneMind phone app, where the contact
// key lives. Calls go through the generated client (@onemind/sdk).
// 25e: every owner sees each running recovery of an account on the box ("Is this you?") and can stop
// it at once (no step-up), and picks the waits: after a contact confirms, and with no contact.
// 25f: legacy contacts (a read-only copy of your files after your death, after a wait you pick) and the
// household's view of claims: owners cancel (and may block), an adult can be the second person.
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { href } from '../shell/routes';

type Contact = components['schemas']['ContactView'];
type Added = components['schemas']['ContactAdded'];
type Waits = components['schemas']['RecoverySettings'];
type Invitation = components['schemas']['Invitation'];
type Recovery = components['schemas']['RecoveryView'];
type Legacy = components['schemas']['LegacyView'];
type LegacyAdded = components['schemas']['LegacyAdded'];
type LegacyInviteRequest = components['schemas']['LegacyInviteRequest'];
type Claim = components['schemas']['ClaimView'];
const WAIT_LABEL: Record<string, string> = { contact_wait_hours: 'Wait after a contact confirms', remote_wait_hours: 'Wait with no contact' };

const STATE: Record<string, string> = {
  invited: 'Invited', expired: 'Invite expired', cooling_off: 'Accepted, not counting yet', active: 'Active',
  removed: 'Removed', resigned: 'Stepped down',
};

// usePoll keeps only ApiError details, so reads carry the gateway's status across.
function checked<T>(request: Promise<T>): Promise<T> {
  return request.catch((error: unknown) => {
    if (error instanceof OneMindError) {
      throw new ApiError(error.status, error.status === 401 ? 'unauthenticated' : error.status === 403 ? 'permission_denied' : 'unknown', error.message, error.reason);
    }
    throw error;
  });
}

function why(error: unknown): string {
  if (error instanceof OneMindError || error instanceof ApiError) {
    if (error.reason === 'step_up_required') return 'This needs a fresh passkey sign-in. Sign out and sign in with your passkey, then try again.';
    if (error.status === 403) return 'Only an owner, signed in on this device, can manage recovery contacts.';
    return error.message;
  }
  return 'Something went wrong.';
}

function useSdk() {
  const { token } = useSignedIn();
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
}

// D-028 holds new invites and invite pickup until the shared enrollment checks are available.
export function RecoveryContacts({ legacyEnrollmentAvailable = false }: { legacyEnrollmentAvailable?: boolean } = {}) {
  const { role } = useShell();
  if (role === 'owner') return <><RunningRecoveries /><LegacyClaims owner /><OwnerContacts /><LegacyContacts enrollmentAvailable={legacyEnrollmentAvailable} /></>;
  return <><MyInvitations />{role === 'adult' && <LegacyClaims owner={false} />}</>;
}

function RunningRecoveries() {
  const sdk = useSdk();
  const running = usePoll(() => checked(sdk.call<Recovery[]>({ method: 'GET', path: '/v1/auth/recovery' })), 30_000);
  const [error, setError] = useState('');
  if (!running.data?.length) return null;
  const cancel = async (r: Recovery) => {
    setError('');
    try {
      await sdk.call<Recovery>({ method: 'POST', path: `/v1/auth/recovery/requests/${encodeURIComponent(r.id)}/cancel` });
      await running.reload();
    } catch (e) {
      setError(why(e));
    }
  };
  return (
    <Card title="Recovery in progress" subtitle="Someone is getting back into an account on this box. If it is not you or someone you know, stop it now.">
      <ul aria-label="Running recoveries">
        {running.data.map((r) => (
          <li key={r.id}>
            {r.path === 'contact' ? 'With a recovery contact' : 'With no contact'} · {r.state === 'waiting' && r.not_before ? `can finish after ${new Date(r.not_before).toLocaleString()}` : 'waiting for a contact'} · from {r.source}
            <Button size="sm" aria-label={`Stop recovery ${r.id}`} onClick={() => void cancel(r)}>Stop it</Button>
          </li>
        ))}
      </ul>
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function OwnerContacts() {
  const sdk = useSdk();
  const contacts = usePoll(() => checked(sdk.call<Contact[]>({ method: 'GET', path: '/v1/auth/recovery/contacts' })), 0);
  const waits = usePoll(() => checked(sdk.call<Waits>({ method: 'GET', path: '/v1/auth/recovery/settings' })), 0);
  const [name, setName] = useState('');
  const [cooling, setCooling] = useState<number | ''>('');
  const [invite, setInvite] = useState<Added | null>(null);
  const [error, setError] = useState('');
  const options = waits.data?.options.cooling_off_days ?? [3, 7, 14];
  const current = waits.data?.values.cooling_off_days;

  const act = async (job: () => Promise<unknown>) => {
    setError('');
    try {
      await job();
      await Promise.all([contacts.reload(), waits.reload()]);
    } catch (e) {
      setError(why(e));
    }
  };
  const add = () => act(async () => {
    const body: Record<string, unknown> = { kind: 'outside', display_name: name.trim() };
    if (cooling !== '') body.cooling_off_days = cooling;
    setInvite(await sdk.call<Added>({ method: 'POST', path: '/v1/auth/recovery/contacts', body }));
    setName('');
  });
  const remove = (c: Contact) => act(() => sdk.call<Contact>({ method: 'DELETE', path: `/v1/auth/recovery/contacts/${encodeURIComponent(c.id)}` }));
  const setDefault = (days: number) => act(() => sdk.call<Waits>({ method: 'PUT', path: '/v1/auth/recovery/settings', body: { cooling_off_days: days } }));
  const setWait = (key: string, value: number) => act(() => sdk.call<Waits>({ method: 'PUT', path: '/v1/auth/recovery/settings', body: { [key]: value } }));

  return (
    <Card title="Recovery contacts" subtitle="Up to 5 people who can confirm it is really you if you are locked out. They never see your files and cannot approve anything.">
      {contacts.error ? <p role="alert">{why(contacts.error)}</p> : !contacts.data ? <p role="status">Loading recovery contacts…</p> : contacts.data.length === 0 ? (
        <p className="om-hint">No recovery contacts yet.</p>
      ) : (
        <ul aria-label="Recovery contacts">
          {contacts.data.map((c) => (
            <li key={c.id}>
              <strong>{c.display_name}</strong> · {STATE[c.state] ?? c.state}
              {c.usable_at && c.state === 'cooling_off' ? ` · counts from ${new Date(c.usable_at).toLocaleDateString()}` : ''}
              {(c.state === 'invited' || c.state === 'cooling_off' || c.state === 'active') && (
                <Button size="sm" variant="ghost" aria-label={`Remove ${c.display_name}`} onClick={() => void remove(c)}>Remove</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={(e) => { e.preventDefault(); void add(); }}>
        <label>Name <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required /></label>
        <label>Counts after{' '}
          <select aria-label="Cooling-off for this contact" value={cooling} onChange={(e) => setCooling(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">Your default{current ? ` (${current} days)` : ''}</option>
            {options.map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
        <Button type="submit" size="sm" icon="plus">Invite</Button>
      </form>
      {current !== undefined && (
        <label>Default cooling-off{' '}
          <select aria-label="Default cooling-off" value={current} onChange={(e) => void setDefault(Number(e.target.value))}>
            {options.map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
      )}
      {waits.data && Object.keys(WAIT_LABEL).map((key) => waits.data && key in waits.data.values && (
        <label key={key}>{WAIT_LABEL[key]}{' '}
          <select aria-label={WAIT_LABEL[key]} value={waits.data.values[key]} onChange={(e) => void setWait(key, Number(e.target.value))}>
            {(waits.data.options[key] ?? []).map((h) => <option key={h} value={h}>{h % 24 === 0 && h > 72 ? `${h / 24} days` : `${h} hours`}</option>)}
          </select>
        </label>
      ))}
      {invite && (
        <div role="region" aria-label="Invite to send">
          <p>Send this invite to {invite.display_name}. They open it in the OneMind phone app. It works once and expires {new Date(invite.invite_expires_at).toLocaleDateString()}.</p>
          <textarea readOnly value={invite.invite} aria-label="Invite text" rows={3} />
          <p className="om-hint">Box key {invite.box_key_fingerprint}</p>
          <Button size="sm" variant="ghost" onClick={() => setInvite(null)}>Done</Button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function MyInvitations() {
  const sdk = useSdk();
  const list = usePoll(() => checked(sdk.call<Invitation[]>({ method: 'GET', path: '/v1/auth/recovery/invitations' })), 0);
  if (!list.data?.length) return null;
  return (
    <Card title="Recovery contact invitations">
      <ul>
        {list.data.map((i) => (
          <li key={i.id}>{i.owner_display_name ?? 'An owner'} asked you to be a recovery contact. Accept in the OneMind phone app before {new Date(i.invite_expires_at).toLocaleDateString()}.</li>
        ))}
      </ul>
    </Card>
  );
}

function LegacyContacts({ enrollmentAvailable }: { enrollmentAvailable: boolean }) {
  const sdk = useSdk();
  const list = usePoll(() => checked(sdk.call<Legacy[]>({ method: 'GET', path: '/v1/auth/legacy/contacts' })), 0);
  const [name, setName] = useState('');
  const [wait, setWait] = useState(30);
  const [invite, setInvite] = useState<LegacyAdded | null>(null);
  const [approval, setApproval] = useState<string>();
  const [error, setError] = useState('');
  const act = async (job: () => Promise<unknown>) => {
    setError('');
    try {
      await job();
      await list.reload();
    } catch (e) {
      setError(why(e));
    }
  };
  return (
    <Card title="Legacy contacts" subtitle="People who may get a read-only copy of your files after your death. A claim waits, everyone in the household is told, and any sign-in by you cancels it.">
      {!enrollmentAvailable && <p className="om-hint">Legacy contact enrollment is on hold until OneMind supports verification with a hardware key or first-key setup at the box.</p>}
      {list.data && list.data.length > 0 && (
        <ul aria-label="Legacy contacts">
          {list.data.map((c) => (
            <li key={c.id}>
              <strong>{c.display_name}</strong> · {STATE[c.state] ?? c.state} · claim waits {c.wait_days} days
              {enrollmentAvailable && c.state === 'invited' && (
                <Button size="sm" variant="ghost" aria-label={`Show legacy invite for ${c.display_name}`} onClick={() => void act(async () => {
                  setInvite(await sdk.call<LegacyAdded>({ method: 'GET', path: `/v1/auth/legacy/contacts/${encodeURIComponent(c.id)}/invite` }));
                })}>Show invite</Button>
              )}
              {(c.state === 'invited' || c.state === 'cooling_off' || c.state === 'active') && (
                <Button size="sm" variant="ghost" aria-label={`Remove legacy contact ${c.display_name}`} onClick={() => void act(() => sdk.call({ method: 'DELETE', path: `/v1/auth/legacy/contacts/${encodeURIComponent(c.id)}` }))}>Remove</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {enrollmentAvailable && <form onSubmit={(e) => { e.preventDefault(); void act(async () => {
        const queued = await sdk.call<LegacyInviteRequest>({ method: 'POST', path: '/v1/auth/legacy/contacts', body: { kind: 'outside', display_name: name.trim(), wait_days: wait } });
        setApproval(queued.action_id);
        setName('');
      }); }}>
        <label>Legacy contact name <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required /></label>
        <label>Claim wait{' '}
          <select aria-label="Claim wait" value={wait} onChange={(e) => setWait(Number(e.target.value))}>
            {[14, 30, 60, 90].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
        <Button type="submit" size="sm" icon="plus">Request legacy invite</Button>
      </form>}
      {approval && <p role="status"><Link to={href.approval(approval)}>Review legacy invite</Link> with your passkey. Then return here to copy it.</p>}
      {invite && (
        <div role="region" aria-label="Legacy invite to send">
          <p>Send this invite to {invite.display_name}; they open it in the OneMind phone app, which keeps their access key.</p>
          <textarea readOnly value={invite.invite} aria-label="Legacy invite text" rows={3} />
          <Button size="sm" variant="ghost" onClick={() => setInvite(null)}>Done</Button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function LegacyClaims({ owner }: { owner: boolean }) {
  const sdk = useSdk();
  const claims = usePoll(() => checked(sdk.call<Claim[]>({ method: 'GET', path: '/v1/auth/legacy/claims' })), 60_000);
  const [error, setError] = useState('');
  const open = claims.data?.filter((c) => c.state === 'waiting' || c.state === 'awaiting_second' || (owner && c.state === 'granted')) ?? [];
  if (open.length === 0) return null;
  const act = async (path: string, body?: unknown) => {
    setError('');
    try {
      await sdk.call({ method: 'POST', path, body });
      await claims.reload();
    } catch (e) {
      setError(why(e));
    }
  };
  return (
    <Card title="Legacy access requested" subtitle="Someone says an owner has died and asks for a copy of their files. OneMind cannot check the certificate.">
      <ul aria-label="Legacy claims">
        {open.map((c) => (
          <li key={c.id}>
            {c.contact_display_name ?? 'A legacy contact'} · {c.state === 'granted' ? `export open until ${new Date(c.access_until ?? c.ends_at).toLocaleDateString()}` : `can be granted after ${new Date(c.ends_at).toLocaleDateString()}`}
            {c.needs_second && !c.second_confirmed ? ' · needs a second person' : ''}
            {c.second_confirmed && c.confirmed_by_display_name ? ` · confirmed by ${c.confirmed_by_display_name}` : ''}
            {c.claimant_accepted_signed_in === false ? ' · accepted on a signed-out phone: make sure the second person is someone else' : ''}
            {owner && <Button size="sm" aria-label={`Cancel claim ${c.id}`} onClick={() => void act(`/v1/auth/legacy/claims/${encodeURIComponent(c.id)}/cancel`, { block: false })}>Cancel</Button>}
            {owner && <Button size="sm" variant="ghost" aria-label={`Cancel and block ${c.id}`} onClick={() => void act(`/v1/auth/legacy/claims/${encodeURIComponent(c.id)}/cancel`, { block: true })}>Cancel and block</Button>}
            {!owner && c.needs_second && !c.second_confirmed && <Button size="sm" variant="ghost" aria-label={`Confirm claim ${c.id}`} onClick={() => void act(`/v1/auth/legacy/claims/${encodeURIComponent(c.id)}/confirm`)}>Confirm as second person</Button>}
          </li>
        ))}
      </ul>
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

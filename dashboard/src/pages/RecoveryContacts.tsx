// SPDX-License-Identifier: Apache-2.0
// Settings > Account: recovery contacts (gateway permissions design 25d, D-028). An owner invites up
// to 5 people who can later confirm a recovery. They never see your data or approve anything. Adding
// one, or shortening the cooling-off, needs a fresh passkey sign-in; removing one does not. A household
// adult sees the invitations addressed to them and accepts in the OneMind phone app, where the contact
// key lives. Calls go through the generated client (@onemind/sdk).
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';

type Contact = components['schemas']['ContactView'];
type Added = components['schemas']['ContactAdded'];
type Waits = components['schemas']['RecoverySettings'];
type Invitation = components['schemas']['Invitation'];

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

export function RecoveryContacts() {
  const { role } = useShell();
  return role === 'owner' ? <OwnerContacts /> : <MyInvitations />;
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

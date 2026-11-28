// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { useNow, usePoll } from '../lib/hooks';

type Settings = components['schemas']['OnboardingSettingsView'];
type SettingsBody = components['schemas']['OnboardingSettingsBody'];
type Controls = components['schemas']['SystemControls'];

function useSdk() {
  const { token } = useSignedIn();
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
}

function failure(error: ApiError) {
  return error.status === 403 ? 'Owner only' : 'Unknown';
}

function checked<T>(request: Promise<T>) {
  return request.catch((error: unknown) => {
    if (error instanceof OneMindError) throw new ApiError(error.status, error.status === 401 ? 'unauthenticated' : error.status === 403 ? 'permission_denied' : 'unknown', error.message);
    throw error;
  });
}

export function SettingsDateTime() {
  const api = useSdk();
  const { role } = useShell();
  const now = useNow(1000);
  const settings = usePoll(() => checked(api.call<Settings>({ method: 'GET', path: '/v1/onboarding/settings' })), 0);
  const clock = usePoll(async () => {
    await checked(api.instance.get());
    return api.hubOffsetMs();
  }, 30_000);
  const [draft, setDraft] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const form = async (event: FormEvent) => {
    event.preventDefault();
    if (role !== 'owner' || !settings.data?.box_name || !draft || saving) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const current = await api.call<Settings>({ method: 'GET', path: '/v1/onboarding/settings' });
      if (!current.box_name || !current.saved) throw new Error('Finish the box setup before changing its time zone.');
      const body: SettingsBody = {
        box_name: current.box_name, time_zone: draft, backup_choice: current.backup_choice,
        backup_destination_id: current.backup_destination_id,
      };
      const result = await api.call<Settings>({ method: 'PUT', path: '/v1/onboarding/settings', body });
      if (result.time_zone !== draft) throw new Error('The hub did not confirm the new time zone.');
      setDraft(undefined);
      setNotice('Time zone saved.');
      await settings.reload();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not save time zone.');
    } finally {
      setSaving(false);
    }
  };
  const offset = clock.data;
  const zone = settings.data?.time_zone;
  return <>
    <PageHeader title="Date and time" />
    <Card title="Hub clock">
      <dl>
        <dt>Current time</dt><dd>{offset === undefined || clock.error ? 'Unknown' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium', timeZone: zone || 'UTC' }).format(now + offset)}</dd>
        <dt>Time zone</dt><dd>{settings.error ? failure(settings.error) : zone ?? 'Unknown'}</dd>
        <dt>Clock synchronisation</dt><dd>Not reported by this hub yet</dd>
      </dl>
      {offset !== undefined && !clock.error && Math.abs(offset) > 120_000 && <p role="alert">Your device clock differs from the hub by {Math.round(Math.abs(offset) / 1000)} seconds. Sign-in codes may fail.</p>}
      {role === 'owner' && zone && settings.data?.saved && <form onSubmit={(event) => void form(event)}>
        <label htmlFor="hub-time-zone">Time zone</label>
        <input id="hub-time-zone" value={draft ?? zone} onChange={(event) => setDraft(event.target.value)} required />
        <Button type="submit" disabled={!draft || draft === zone || saving}>Save time zone</Button>
      </form>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </Card>
  </>;
}

/** GET /v1/backups/kit (design 25a): never the key, only where it is and whether the kit printed the disk key. */
interface KitView { state?: string; missing_on?: string[]; disk_key?: string | null }

const DISK_KEY: Record<string, string> = {
  included: 'In the kit', earlier_kit: 'In an earlier kit', not_encrypted: 'Not needed (disk not encrypted)', not_available: 'Not in the kit',
};

/** Adds the printed owner key to backup destinations added after the kit (POST /v1/backups/kit/attach). */
function KitAttach({ api, missing, onDone }: { api: OneMind; missing: number; onDone: () => Promise<void> }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const groups = text.toUpperCase().match(/\b[A-Z2-7]{4}\b/g) ?? [];
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (groups.length !== 14 || busy) return;
    setBusy(true);
    setError('');
    try {
      await api.call<unknown>({ method: 'POST', path: '/v1/backups/kit/attach', body: { groups: groups.slice(0, 13), check: groups[13] } });
      setText(''); // the key never outlives the request
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add the key.');
    } finally {
      setBusy(false);
    }
  };
  return <form onSubmit={(event) => void submit(event)}>
    <p role="alert">{missing} backup destination{missing === 1 ? ' was' : 's were'} added after your kit. Type the key from your kit to let it open {missing === 1 ? 'it' : 'them'} too.</p>
    <label htmlFor="kit-attach-key">Owner recovery key and check group</label>
    <textarea id="kit-attach-key" value={text} autoComplete="off" spellCheck={false} onChange={(event) => setText(event.target.value)} />
    <Button type="submit" disabled={groups.length !== 14 || busy}>Add the key to the new destinations</Button>
    {error && <p role="alert">{error}</p>}
  </form>;
}

export function SettingsRecoveryReset() {
  const api = useSdk();
  const { role } = useShell();
  const kit = usePoll(() => checked(api.call<KitView>({ method: 'GET', path: '/v1/backups/kit' })), 0);
  const backup = usePoll(() => checked(api.call<unknown>({ method: 'GET', path: '/v1/backups/status' })), 0);
  const controls = usePoll(() => checked(api.call<Controls>({ method: 'GET', path: '/v1/system/controls' })), 0);
  const kitState = kit.data?.state;
  const missing = kit.data?.missing_on ?? [];
  const diskKey = kit.data?.disk_key;
  const last = backup.data && typeof backup.data === 'object' && 'last_verified_restore_at' in backup.data
    ? backup.data.last_verified_restore_at : undefined;
  const kitLabel = kitState === 'missing' ? 'Missing' : kitState === 'issued' ? 'Needs confirmation' : kitState === 'confirmed' ? 'Confirmed' : 'Unknown';
  return <>
    <PageHeader title="Recovery and reset" />
    <Card title="Recovery">
      <dl>
        <dt>Emergency Kit</dt><dd>{kit.error ? failure(kit.error) : kitLabel}</dd>
        {!kit.error && kitState && kitState !== 'missing' && <><dt>Disk recovery key</dt><dd>{diskKey ? DISK_KEY[diskKey] ?? 'Unknown' : 'Unknown'}</dd></>}
        <dt>Last verified restore</dt><dd>{backup.error ? failure(backup.error) : typeof last === 'string' ? last : last === null ? 'No verified restore' : 'Unknown'}</dd>
      </dl>
      {role === 'owner' && missing.length > 0 && <KitAttach api={api} missing={missing.length} onDone={kit.reload} />}
      <div className="dash-actions"><Link to="/backups">Backups and Emergency Kit</Link><Link to="/settings/storage">Storage recovery key</Link></div>
    </Card>
    <Card title="Restart, shutdown and reset">
      <p>Factory reset needs an owner’s passkey. File and review system requests in Troubleshoot.</p>
      {controls.error ? <p>{failure(controls.error)}</p> : controls.data
        ? <ul>{controls.data.controls.map((control) => <li key={control.type}>{control.label} · {control.available ? 'Available to request' : control.unavailable_reason ?? 'Unavailable'}</li>)}</ul>
        : <p>Checking system controls…</p>}
      <div className="dash-actions"><Link to="/troubleshoot">Open system controls</Link><Link to="/settings/about">Help and rescue console</Link></div>
    </Card>
  </>;
}

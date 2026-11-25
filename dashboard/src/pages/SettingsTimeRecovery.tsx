// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { useNow, usePoll } from '../lib/hooks';

type Settings = components['schemas']['OnboardingSettingsView'];
type SetZoneBody = components['schemas']['SetZoneRequest'];
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

type TimeView = components['schemas']['TimeView'];
type ActionView = components['schemas']['Action'];
// States an action never leaves (the gateway's ledger); anything else is still in flight.
const FINAL_STATES = ['succeeded', 'failed', 'cancelled', 'expired', 'outcome_unknown'];
const resultMessage = (a: ActionView): string | undefined => (typeof a.result?.message === 'string' ? a.result.message : undefined);

function syncLabel(time: TimeView | undefined, error: ApiError | undefined) {
  if (error) return failure(error);
  if (!time) return 'Checking…';
  if (!time.available) return time.message ?? 'Not reported by this hub';
  if (time.ntp_synchronized === true) return 'Synchronised with a time server';
  if (time.ntp_synchronized === false) return time.ntp_enabled === false ? 'Not synchronised: network time is switched off' : 'Not synchronised yet: no time server reached';
  return 'Not reported by this hub';
}

function zoneChoices(): string[] {
  try {
    return (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone') ?? [];
  } catch {
    return [];
  }
}

export function SettingsDateTime() {
  const api = useSdk();
  const { role } = useShell();
  const now = useNow(1000);
  const settings = usePoll(() => checked(api.call<Settings>({ method: 'GET', path: '/v1/onboarding/settings' })), 0);
  const time = usePoll(() => checked(api.call<TimeView>({ method: 'GET', path: '/v1/system/time' })), 30_000);
  const clock = usePoll(async () => {
    await checked(api.instance.get());
    return api.hubOffsetMs();
  }, 30_000);
  const [draft, setDraft] = useState<string>();
  const [pending, setPending] = useState<ActionView>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const choices = useMemo(zoneChoices, []);
  const reloadTime = time.reload;
  // After the request is filed, follow it until the owner approved it and the host applied it (or it failed).
  useEffect(() => {
    if (!pending || FINAL_STATES.includes(pending.state)) return;
    const timer = setInterval(() => {
      api.call<ActionView>({ method: 'GET', path: `/v1/actions/${encodeURIComponent(pending.id)}` })
        .then((next) => setPending(next)).catch(() => undefined);
    }, 3000);
    return () => clearInterval(timer);
  }, [api, pending]);
  const pendingState = pending?.state;
  useEffect(() => {
    if (pendingState === 'succeeded') void reloadTime();
  }, [pendingState, reloadTime]);
  const view = time.data?.available ? time.data : undefined;
  const zone = view?.zone ?? settings.data?.time_zone ?? undefined;
  const form = async (event: FormEvent) => {
    event.preventDefault();
    if (role !== 'owner' || !draft || saving) return;
    setSaving(true);
    setError('');
    try {
      const body: SetZoneBody = { zone: draft };
      const action = await api.call<ActionView>({ method: 'POST', path: '/v1/system/time/zone', body });
      setPending(action);
      setDraft(undefined);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not request the time zone change.');
    } finally {
      setSaving(false);
    }
  };
  const offset = clock.data;
  const last = view?.last_sync_at ? new Date(view.last_sync_at) : undefined;
  return <>
    <PageHeader title="Date and time" />
    <Card title="Hub clock">
      <dl>
        <dt>Current time</dt><dd>{offset === undefined || clock.error ? 'Unknown' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium', timeZone: zone || 'UTC' }).format(now + offset)}</dd>
        <dt>Time zone</dt><dd>{zone ?? (settings.error ? failure(settings.error) : 'Unknown')}</dd>
        <dt>Clock synchronisation</dt><dd>{syncLabel(time.data, time.error)}</dd>
        {view?.server && <><dt>Time server</dt><dd>{view.server}{typeof view.stratum === 'number' ? ` (stratum ${view.stratum})` : ''}</dd></>}
        {last && !Number.isNaN(last.getTime()) && <><dt>Last synchronised</dt><dd>{last.toLocaleString()}</dd></>}
      </dl>
      {offset !== undefined && !clock.error && Math.abs(offset) > 120_000 && <p role="alert">Your device clock differs from the hub by {Math.round(Math.abs(offset) / 1000)} seconds. Sign-in codes may fail.</p>}
      {role === 'owner' && view && <form onSubmit={(event) => void form(event)}>
        <label htmlFor="hub-time-zone">Time zone</label>
        <input id="hub-time-zone" list="hub-time-zones" value={draft ?? zone ?? ''} onChange={(event) => setDraft(event.target.value)} required />
        <datalist id="hub-time-zones">{choices.map((name) => <option key={name} value={name} />)}</datalist>
        <Button type="submit" disabled={!draft || draft === zone || saving}>Request time zone change</Button>
      </form>}
      {pending && <p role="status">{pending.state === 'succeeded' ? 'Time zone changed.' : pending.state === 'failed' ? `The change failed: ${resultMessage(pending) ?? 'the hub could not apply it'}` : pending.state === 'outcome_unknown' ? 'The hub could not confirm whether the change was applied. Check the time zone above.' : pending.state === 'awaiting_approval' ? 'Waiting for an owner to approve it in Approvals.' : `Time zone change: ${pending.state.replace(/_/g, ' ')}.`}</p>}
      {pending?.state === 'awaiting_approval' && <div className="dash-actions"><Link to="/approvals">Open Approvals</Link></div>}
      {error && <p role="alert">{error}</p>}
    </Card>
  </>;
}

export function SettingsRecoveryReset() {
  const api = useSdk();
  const kit = usePoll(() => checked(api.call<unknown>({ method: 'GET', path: '/v1/backups/kit' })), 0);
  const backup = usePoll(() => checked(api.call<unknown>({ method: 'GET', path: '/v1/backups/status' })), 0);
  const controls = usePoll(() => checked(api.call<Controls>({ method: 'GET', path: '/v1/system/controls' })), 0);
  const kitState = kit.data && typeof kit.data === 'object' && 'state' in kit.data ? kit.data.state : undefined;
  const last = backup.data && typeof backup.data === 'object' && 'last_verified_restore_at' in backup.data
    ? backup.data.last_verified_restore_at : undefined;
  const kitLabel = kitState === 'missing' ? 'Missing' : kitState === 'issued' ? 'Needs confirmation' : kitState === 'confirmed' ? 'Confirmed' : 'Unknown';
  return <>
    <PageHeader title="Recovery and reset" />
    <Card title="Recovery">
      <dl>
        <dt>Emergency Kit</dt><dd>{kit.error ? failure(kit.error) : kitLabel}</dd>
        <dt>Last verified restore</dt><dd>{backup.error ? failure(backup.error) : typeof last === 'string' ? last : last === null ? 'No verified restore' : 'Unknown'}</dd>
      </dl>
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

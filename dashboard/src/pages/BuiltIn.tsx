// SPDX-License-Identifier: Apache-2.0
// Built in (#617): the apps that ship with OneMind OS, from GET /v1/system-apps through @onemind/sdk.
// Shown twice, from the same component: the Market's Built in tab (/built-in) and Settings → Apps.
// A built-in app is never uninstalled; some can be switched off. Switching off first says what else
// stops, then files an app.disable request that waits in Approvals: nothing changes until an owner
// approves it there. Apps that can never be switched off (Files, Approvals, Settings, Market...) show
// no switch at all.
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, Dialog, PageHeader, StatusPill, useToast } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useHub } from '../data/hub';
import { appDeepLink, appWebPath } from '../lib/appLinks';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { StoreTabs } from './Market';
import { PhotosSwitchCard } from './PhotosSwitch';
import { Load, useRun } from './parts';

export type SystemAppRow = components['schemas']['SystemAppRow'];
interface Dependent { id: string; name: string | null }
/** What else stops when an app is switched off, read before anything is filed. */
interface Stops { row: SystemAppRow; dependents: Dependent[] | null }

function fail(status: number, e: unknown): never {
  if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : e.status === 404 ? 'not_found' : 'unknown', e.message, e.reason);
  if (e instanceof ApiError) throw e;
  throw new ApiError(status, 'unknown', String(e));
}

/** GET /v1/system-apps, checked row by row: a malformed answer is an error, never a half-drawn list. */
export async function readSystemApps(client: OneMind): Promise<SystemAppRow[]> {
  let value: unknown;
  try { value = await client.call<unknown>({ method: 'GET', path: '/v1/system-apps' }); } catch (e) { fail(0, e); }
  const ok = (r: unknown): r is SystemAppRow => {
    const x = r as Record<string, unknown> | null;
    return !!x && typeof x.id === 'string' && typeof x.name === 'string' && (x.kind === 'container' || x.kind === 'native')
      && (x.disable === 'allowed' || x.disable === 'never') && typeof x.enabled === 'boolean' && typeof x.can_disable === 'boolean';
  };
  if (!Array.isArray(value) || !value.every(ok)) throw new ApiError(200, 'unknown', 'The hub returned an invalid list of built-in apps.');
  return value;
}

/**
 * The installed apps that stop working with this one (GET /v1/apps/<id>/dependencies). A native app is
 * part of the OS, not a catalog app, so the hub keeps no dependency list for it: null, not "none".
 */
export async function readDependents(client: OneMind, row: SystemAppRow): Promise<Dependent[] | null> {
  if (row.kind !== 'container') return null;
  let value: unknown;
  try { value = await client.call<unknown>({ method: 'GET', path: `/v1/apps/${encodeURIComponent(row.id)}/dependencies` }); } catch (e) { fail(0, e); }
  const deps = (value as { dependents?: unknown } | null)?.dependents;
  if (!Array.isArray(deps) || !deps.every((d) => d && typeof (d as Dependent).id === 'string')) throw new ApiError(200, 'unknown', 'The hub returned an invalid dependency list.');
  return deps as Dependent[];
}

const CHANNEL: Record<string, string> = { os: 'With the OS', stable: 'Stable', security: 'Security fixes only' };
const channel = (c: string | null | undefined) => (c ? CHANNEL[c] ?? c : 'Not reported');
const licence = (r: SystemAppRow) => r.license ?? (r.kind === 'native' ? 'Part of OneMind OS' : 'Not reported');
const day = (iso: string | null | undefined) => (iso && !Number.isNaN(Date.parse(iso)) ? iso.slice(0, 10) : null);

/** The Market's Built in tab. */
export function BuiltInTab() {
  return (
    <>
      <PageHeader title="Market" lede="Apps that come with OneMind OS. They are never uninstalled; some can be switched off, and an owner approves that first." />
      <StoreTabs current="builtin" />
      <BuiltInApps />
    </>
  );
}

/** Settings → Apps. */
export function SettingsApps() {
  return (
    <div className="dash-stack">
      <h2>Built-in apps</h2>
      <p className="om-hint">Apps that come with OneMind OS: their version, how they update and their licence. Switching one off keeps its data; an owner approves it first.</p>
      <BuiltInApps />
    </div>
  );
}

export function BuiltInApps() {
  const { token, person, mock } = useSignedIn();
  return mock
    ? <p role="status">Connect to a real hub to see its built-in apps. Demo mode has no system app list.</p>
    : <LiveBuiltIn key={person} token={token} />;
}

function LiveBuiltIn({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const rows = usePoll(() => readSystemApps(client), 30_000);
  const hub = useHub();
  const run = useRun();
  const toast = useToast();
  const navigate = useNavigate();
  const [stops, setStops] = useState<Stops>();
  const [busy, setBusy] = useState<string>();
  const canRequest = hub.canRequest !== 'no';
  const waiting = (id: string) => hub.actionList.find((a) => ((a.type as string) === 'app.disable' || (a.type as string) === 'app.enable') && a.params.app_id === id && (a.state === 'requested' || a.state === 'awaiting_approval'));

  const file = async (type: 'app.disable' | 'app.enable', row: SystemAppRow) => {
    setBusy(row.id);
    try {
      const action = await run(async () => {
        try { return await client.actions.request({ type, appId: row.id }); } catch (e) { return fail(0, e); }
      }, type === 'app.disable' ? `Could not ask to switch off ${row.name}` : `Could not ask to switch on ${row.name}`);
      if (!action) return;
      toast.show({ tone: 'info', title: 'Request sent', body: 'It waits in Approvals until an owner decides. Nothing changes before that.' });
      void hub.actions.reload();
      navigate(href.approval(action.id));
    } finally {
      setBusy(undefined);
    }
  };

  // Switching off: read what else stops first, show it, and only then offer to file the request.
  const askOff = (row: SystemAppRow) => void run(async () => {
    setBusy(row.id);
    try { setStops({ row, dependents: await readDependents(client, row) }); } finally { setBusy(undefined); }
  }, `Could not check what ${row.name} is needed by`);

  return (
    <Load res={rows} what="Loading built-in apps">{(list) => (
      <div className="dash-stack">
        {!canRequest && <p className="om-note om-tone-info" role="note">Only an owner or an adult can ask to switch a built-in app off or on.</p>}
        {list.length === 0 && <p role="status">This hub lists no built-in apps for your account.</p>}
        {list.map((row) => {
          const pending = waiting(row.id);
          const link = appDeepLink(row.id);
          const web = appWebPath(row.id);
          const off = day(row.disabled_at);
          const details = (
            <dl className="om-facts" aria-label={`${row.name} licence card`}>
              <div><dt>Version</dt><dd>{row.version ?? (row.update === 'os' ? 'Same as the OS' : 'Not reported')}</dd></div>
              <div><dt>Update channel</dt><dd>{channel(row.update_channel)}</dd></div>
              <div><dt>Licence</dt><dd>{licence(row)}</dd></div>
              {off && <div><dt>Switched off</dt><dd>{off}</dd></div>}
              {link && <div><dt>Link</dt><dd><code>{link}</code></dd></div>}
            </dl>
          );
          if (row.id === 'photos') return <PhotosSwitchCard key={row.id} client={client} web={web}>{details}</PhotosSwitchCard>;
          return (
            <Card key={row.id} level={3} title={row.name} subtitle={row.kind === 'native' ? 'Part of the system' : 'App, kept up to date like any other'}
              aside={row.can_disable
                ? <StatusPill tone={row.enabled ? 'ok' : 'neutral'} label={row.enabled ? 'On' : 'Off'} />
                : <StatusPill tone="info" label="Always on" />}>
              {details}
              {row.can_disable ? (
                canRequest && (
                  <p className="dash-row">
                    <button type="button" role="switch" className="om-set-switch" aria-checked={row.enabled} aria-label={`${row.name}: ${row.enabled ? 'on' : 'off'}`}
                      disabled={!!pending || busy === row.id} onClick={() => (row.enabled ? askOff(row) : void file('app.enable', row))}>
                      <span className="om-set-switch-thumb" aria-hidden="true" />
                    </button>{' '}
                    {pending ? <span role="status">Waiting for approval</span> : <span className="om-hint">{row.enabled ? 'Switch off (keeps its data)' : 'Switch back on'}</span>}
                  </p>
                )
              ) : (
                <p className="om-hint">Always on: the box needs it to repair itself, so it cannot be switched off.</p>
              )}
              {row.enabled && web && <p className="om-hint"><a href={web}>Open {row.name}</a></p>}
            </Card>
          );
        })}
        {stops && (
          <Dialog open title={`Switch off ${stops.row.name}?`} onClose={() => setStops(undefined)} actions={<>
            <Button onClick={() => setStops(undefined)}>Cancel</Button>
            <Button variant="danger" onClick={() => { const row = stops.row; setStops(undefined); void file('app.disable', row); }}>Ask to switch off</Button>
          </>}>
            <p>What stops when {stops.row.name} is off:</p>
            <ul aria-label="What else stops">
              <li>{stops.row.name} itself: it leaves the dock, search, AI tools and the phone until it is switched back on.</li>
              {stops.dependents?.map((d) => <li key={d.id}>{d.name || d.id} stops working: it needs {stops.row.name}.</li>)}
              {stops.dependents?.length === 0 && <li>No installed app needs it.</li>}
              {stops.dependents === null && <li>Its screen and its onemind:// links stop opening.</li>}
            </ul>
            <p className="om-hint">Its data, settings and secrets are kept. Nothing changes now: an owner approves this in Approvals first.</p>
          </Dialog>
        )}
      </div>
    )}</Load>
  );
}

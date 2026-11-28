// SPDX-License-Identifier: Apache-2.0
// Gateway storage view. Disk changes are only requested from storage/Changes.tsx (plan first, owner approves in Approvals); no recovery keys or device probing in the browser.
import { useMemo } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Link } from 'react-router';
import { Button, Card, EmptyState, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';
import { StorageCare } from './StorageCare';
import { StorageChanges } from './storage/Changes';

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The hub returned an invalid storage record.');
  return value as Record<string, unknown>;
}
function records(value: unknown) {
  if (!Array.isArray(value)) throw new Error('The hub returned an invalid storage list.');
  return value.map(record);
}
function status(value: unknown) {
  const s = record(value);
  if (typeof s.enabled !== 'boolean' || typeof s.available !== 'boolean') throw new Error('The hub returned an invalid storage status.');
  if (s.available) records(s.members);
  return s;
}
function text(value: unknown, missing = 'Not reported') { return typeof value === 'string' && value ? value : missing; }
function number(value: unknown, unit: string) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `${value} ${unit}` : 'Not reported'; }
function messages(value: unknown) { return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string').join('; ') : ''; }
async function read(client: OneMind, path: string) {
  try { return await client.call<unknown>({ method: 'GET', path }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}
export function Storage() {
  const { token, person, mock } = useSignedIn();
  return mock ? <><PageHeader title="Storage" lede="Storage and disk health reported by your hub." /><EmptyState icon="storage" title="No storage reported yet" action={<Link className="om-btn om-btn-primary" to={href.settings}>Open Settings</Link>}>A hub lists its disks and their health once its storage service has reported. Demo mode has no storage data; connect a real hub to see them.</EmptyState></> : <LiveStorage key={person} token={token} />;
}
function LiveStorage({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const summary = usePoll(async () => status(await read(client, '/v1/storage')), 30_000);
  const devices = usePoll(async () => records(await read(client, '/v1/storage/devices')), 30_000);
  return <div className="dash-stack">
    <PageHeader title="Storage" lede="Storage and disk health reported by your hub. Safely removing a USB drive and changing the disks (at the bottom) always wait for an owner's approval." />
    <Button onClick={() => { void summary.reload(); void devices.reload(); }}>Refresh storage</Button>
    {[summary, devices].some((r) => r.error && r.data !== undefined) && <p role="status">Could not refresh. Showing previously fetched storage data; refresh to check again.</p>}
    <Load res={summary} what="Loading storage status">{(s) => <Card as="article" title="Storage health">
      {!s.enabled ? <p>Storage is disabled on this hub.</p> : !s.available ? <p>Storage service unavailable. {text(s.error, '')}</p> : <>
        <dl className="om-facts">
          <div><dt>Node</dt><dd>{text(s.node_id)}</dd></div>
          <div><dt>State</dt><dd>{text(s.state)}</dd></div>
          <div><dt>Encrypted</dt><dd>{typeof s.encrypted === 'boolean' ? s.encrypted ? 'Yes' : 'No' : 'Not reported'}</dd></div>
          <div><dt>Used data</dt><dd>{number(s.used_bytes, 'bytes')}</dd></div>
          <div><dt>Reported at</dt><dd>{text(s.at)}</dd></div>
        </dl>
        {messages(s.reasons) && <p>{messages(s.reasons)}</p>}
        <p>Member capacity and allocation are raw device values, not usable free space.</p>
        <ul>{records(s.members).map((m, i) => <li key={i}>Member {typeof m.devid === 'number' ? m.devid : 'unknown'}{m.missing === true ? ' · missing' : ''} · capacity {number(m.size_bytes, 'bytes')} · allocated {number(m.allocated_bytes, 'bytes')}</li>)}</ul>
      </>}
    </Card>}</Load>
    <Load res={devices} what="Loading owner-only disk health">{(items) => <Card title="Disk health">
      <p>Disk identities are owner-only. Missing SMART data never means a healthy disk.</p>
      {items.length === 0 ? <p>No disks reported.</p> : <ul>{items.map((d, i) => {
        const health = d.health && typeof d.health === 'object' && !Array.isArray(d.health) ? record(d.health) : {};
        return <li key={i}>
          <strong>{text(d.model, text(d.path))}</strong> · {text(d.role)} · {number(d.size_bytes, 'bytes')}
          <dl className="om-facts">
            <div><dt>Device</dt><dd>{text(d.path)}</dd></div>
            <div><dt>Serial ending</dt><dd>{text(d.serial_tail)}</dd></div>
            <div><dt>SMART verdict</dt><dd>{text(health.verdict, 'Unknown')}</dd></div>
            <div><dt>Temperature</dt><dd>{number(health.temperature_c, '°C')}</dd></div>
            <div><dt>Wear</dt><dd>{number(health.wear_percent, '%')}</dd></div>
          </dl>
          {messages(health.reasons) && <p>{messages(health.reasons)}</p>}
        </li>;
      })}</ul>}
    </Card>}</Load>
    <StorageCare client={client} />
    <StorageChanges summary={summary.data} disks={devices.data} />
  </div>;
}

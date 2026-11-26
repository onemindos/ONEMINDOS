// SPDX-License-Identifier: Apache-2.0
// Storage housekeeping (P-10): last TRIM, smartd health warnings and "Safely remove" for USB drives.
// Reads GET /v1/storage/housekeeping. Removing a drive only files a request: an owner approves it in Approvals.
import { useState } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Link } from 'react-router';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { href } from '../shell/routes';
import { Load } from './parts';

type Rec = Record<string, unknown>;
function rec(v: unknown, what: string): Rec {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v as Rec;
}
function list(v: unknown, what: string): Rec[] {
  if (!Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v.map((x) => rec(x, what));
}
function str(v: unknown): string { return typeof v === 'string' ? v : ''; }
function when(v: unknown, none: string) {
  const d = typeof v === 'string' ? new Date(v) : undefined;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleString() : none;
}
function gb(v: unknown) { return typeof v === 'number' && v >= 0 ? `${(v / 1e9).toFixed(1)} GB` : 'size not reported'; }

export function parseHousekeeping(raw: unknown): Rec {
  const v = rec(raw, 'storage housekeeping answer');
  if (typeof v.available !== 'boolean') throw new Error('The hub returned an invalid storage housekeeping answer.');
  if (v.available) {
    rec(v.trim, 'TRIM status');
    list(rec(v.smart, 'smartd status').alerts, 'smartd warning list');
    list(v.removable, 'drive list');
  }
  return v;
}

export function StorageCare({ client }: { client: OneMind }) {
  const res = usePoll(async () => parseHousekeeping(await client.call<unknown>({ method: 'GET', path: '/v1/storage/housekeeping' })), 30_000);
  const [asked, setAsked] = useState<Record<string, { id?: string; error?: string }>>({});
  async function remove(name: string) {
    setAsked((a) => ({ ...a, [name]: {} }));
    try {
      const act = rec(await client.call<unknown>({ method: 'POST', path: `/v1/storage/removable/${encodeURIComponent(name)}/eject`, body: { idempotency_key: `dash-${name}-${Date.now()}` } }), 'request');
      setAsked((a) => ({ ...a, [name]: { id: str(act.id) } }));
    } catch (e) {
      setAsked((a) => ({ ...a, [name]: { error: e instanceof OneMindError ? e.message : 'The hub could not take the request.' } }));
    }
  }
  return <Load res={res} what="Loading TRIM, disk warnings and drives">{(v) => v.available !== true
    ? <Card title="Housekeeping"><p role="status">{str(v.message) || 'The box could not be asked about TRIM and drives.'}</p></Card>
    : <>
      <Card title="SSD housekeeping (TRIM)">
        {(() => {
          const t = rec(v.trim, 'TRIM status');
          return <>
            <dl className="om-facts">
              <div><dt>Weekly TRIM</dt><dd>{t.enabled === true ? 'On' : 'Off'}</dd></div>
              <div><dt>Last TRIM</dt><dd>{t.last_run_at ? `${when(t.last_run_at, 'unknown')}${str(t.last_result) && str(t.last_result) !== 'success' ? ` (${str(t.last_result)})` : ''}` : 'Has not run on this box yet'}</dd></div>
              {typeof t.last_trimmed_bytes === 'number' && <div><dt>Freed last time</dt><dd>{(t.last_trimmed_bytes / 2 ** 30).toFixed(1)} GiB</dd></div>}
              <div><dt>Next TRIM</dt><dd>{when(t.next_run_at, 'Not scheduled')}</dd></div>
            </dl>
            <p>TRIM tells the SSD which blocks are free so it stays fast. It runs weekly on its own; there is nothing to do here.</p>
          </>;
        })()}
      </Card>
      <Card title="Disk health warnings">
        {(() => {
          const s = rec(v.smart, 'smartd status');
          const alerts = list(s.alerts, 'smartd warning list');
          return <>
            <p>The disk watcher (smartd) is {str(s.daemon_state) === 'active' ? 'running' : `not running (${str(s.daemon_state) || 'unknown'})`}. Warnings also arrive in Notifications.</p>
            {alerts.length === 0 ? <p>No warnings from the disk watcher.</p> : <ul>{alerts.map((a) => <li key={str(a.id)}>
              <strong>{str(a.device)}</strong> · {str(a.kind)} · {when(a.at, '')}<br />{str(a.message)}
            </li>)}</ul>}
          </>;
        })()}
      </Card>
      <Card title="USB drives">
        {(() => {
          const drives = list(v.removable, 'drive list');
          if (drives.length === 0) return <p>No USB drive is plugged in.</p>;
          return <ul>{drives.map((d) => {
            const name = str(d.name);
            const state = asked[name];
            return <li key={name}>
              <strong>{str(d.label) || str(d.model) || str(d.device)}</strong> · {str(d.device)} · {gb(d.size_bytes)}
              {d.ejectable === true
                ? state?.id !== undefined
                  ? <p role="status">Waiting for an owner to approve. <Link to={href.approval(state.id)}>Open the approval</Link></p>
                  : <p><Button size="sm" onClick={() => void remove(name)}>Safely remove</Button>{state?.error && <span role="alert"> {state.error}</span>}</p>
                : <p>In use: {str(d.why_not) || 'the box is using this drive'}</p>}
            </li>;
          })}</ul>;
        })()}
      </Card>
    </>}</Load>;
}

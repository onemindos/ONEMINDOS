// SPDX-License-Identifier: Apache-2.0
// Settings > Account and security > My devices (#715, UI parity M4): every phone, browser and app signed in as you,
// from GET /v1/me/devices through @onemind/sdk. "Lost this device" is DELETE /v1/me/devices/{id}: it revokes every
// sign-in, passkey, approver key and push registration the device holds in one step. The gateway decides who may:
// your own session only, a fresh passkey sign-in once the box has passkeys (step_up_required), never the device you
// are using and never the box's last owner passkey. This screen adds no check of its own. The phone app's
// MyDevicesList (mobile/src/screens/DeviceSection.tsx) is the same screen.
import { useState } from 'react';
import type { components } from '@onemind/sdk';
import { Button, Card, StatusPill, Table } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useGateway, viaSdk } from '../lib/gateway';
import { usePoll } from '../lib/hooks';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Load } from './parts';

type Devices = components['schemas']['MyDevices'];
type Device = components['schemas']['MyDevice'];
type Removed = components['schemas']['MyDeviceRemoved'];

const KIND: Record<Device['kind'], string> = { phone: 'Phone', browser: 'Browser', app: 'App', unknown: 'Device' };
const SOURCE: Record<string, [string, string]> = {
  sessions: ['sign-in', 'sign-ins'],
  passkeys: ['passkey', 'passkeys'],
  approver_keys: ['approver key', 'approver keys'],
  push: ['push registration', 'push registrations'],
};

/** What a device holds, in words: "2 sign-ins, 1 passkey". */
export function holds(d: Pick<Device, 'credentials'>): string {
  const n = new Map<string, number>();
  for (const c of d.credentials) n.set(c.source, (n.get(c.source) ?? 0) + 1);
  return [...n].map(([k, v]) => `${v} ${SOURCE[k]?.[v === 1 ? 0 : 1] ?? k}`).join(', ') || 'nothing';
}

function removeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.reason === 'step_up_required') return 'Removing a device needs a fresh passkey sign-in. Sign out, sign in with your passkey, then try again.';
    if (e.reason === 'current_device') return 'This is the device you are using. Sign out here instead.';
    if (e.reason === 'last_owner') return 'This device holds the last owner passkey on the box. Add a passkey on another device first.';
    if (e.reason === 'session_required') return 'This needs you to be signed in on this device. Sign out, sign in again and try once more.';
    if (e.code === 'network') return 'The box did not answer. Nothing was removed; try again.';
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export function MyDevices() {
  const { token, mock } = useSignedIn();
  if (mock) return <Card title="My devices"><p role="status">Connect to a real box to see the devices signed in as you. Demo mode lists none.</p></Card>;
  return <LiveDevices token={token} />;
}

function LiveDevices({ token }: { token: string }) {
  const sdk = useGateway(token);
  const list = usePoll(() => viaSdk(() => sdk.call<Devices>({ method: 'GET', path: '/v1/me/devices' })), 30_000);
  const [asking, setAsking] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'bad'; text: string }>();
  const now = Date.now();

  const remove = async (d: Device) => {
    setBusy(true);
    setMsg(undefined);
    try {
      const r = await viaSdk(() => sdk.call<Removed>({ method: 'DELETE', path: `/v1/me/devices/${encodeURIComponent(d.id)}` }));
      const total = Object.values(r.revoked).reduce((a, b) => a + b, 0);
      setMsg({
        tone: 'ok',
        text: r.removed
          ? `${d.label} is removed: ${total} ${total === 1 ? 'credential' : 'credentials'} revoked. It has to sign in again to use this box.`
          : `${d.label} was already removed. Nothing was left to revoke.`,
      });
      setAsking(undefined);
      await list.reload();
    } catch (e) {
      setMsg({ tone: 'bad', text: removeError(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="My devices" subtitle="Phones, browsers and apps signed in as you">
      <p>If you lose a phone or laptop, remove it here. Everything it holds stops working at once, and it has to sign in again to come back.</p>
      {msg && <p className={`om-note om-tone-${msg.tone}`} role={msg.tone === 'bad' ? 'alert' : 'status'}>{msg.text}</p>}
      <Load res={list} what="Loading your devices">
        {(v) =>
          v.devices.length === 0 ? (
            <p className="om-hint">No devices are signed in as you.</p>
          ) : (
            <Table
              caption="My devices"
              hideCaption
              rows={v.devices}
              rowKey={(d) => d.id}
              columns={[
                {
                  key: 'name',
                  header: 'Device',
                  render: (d) => (
                    <span className="dash-actions">
                      <span>{d.label}</span>
                      <StatusPill tone="neutral" label={KIND[d.kind]} />
                      {d.current && <StatusPill tone="ok" label="In use here" />}
                    </span>
                  ),
                },
                { key: 'seen', header: 'Last seen', render: (d) => (d.last_seen_at ? formatAgo(secondsSince(d.last_seen_at, now)) : 'unknown'), secondary: true },
                { key: 'holds', header: 'Holds', render: (d) => holds(d), secondary: true },
                {
                  key: 'x',
                  header: 'Actions',
                  render: (d) =>
                    d.current ? null : asking === d.id ? (
                      <span className="dash-actions" role="group" aria-label={`Remove ${d.label}?`}>
                        <Button size="sm" variant="danger" disabled={busy} onClick={() => void remove(d)}>{busy ? 'Removing…' : `Remove ${d.label}`}</Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setAsking(undefined)}>Keep it</Button>
                      </span>
                    ) : (
                      <Button size="sm" variant="ghost" disabled={busy} aria-label={`Lost this device: ${d.label}`} onClick={() => { setMsg(undefined); setAsking(d.id); }}>
                        Lost this device
                      </Button>
                    ),
                },
              ]}
            />
          )
        }
      </Load>
    </Card>
  );
}

// SPDX-License-Identifier: Apache-2.0
// Settings > About > Security events (#620, NATS plan N3): who connected to the message bus and who was
// refused, from GET /v1/fabric/events. Read-only: the hub's observer writes the lines, nothing here can
// change a key. Alerts for an unknown device, a removed machine that keeps trying and a machine that keeps
// dropping go to the inbox under "security" (Settings > Notifications turns that topic on or off).
// Needs audit:read: a child, teen or guest has none, so the card is simply not there for them.
import { useMemo } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Card, StatusPill, Table, type Column } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

type BusEvents = components['schemas']['FabricEvents'];
type BusEvent = components['schemas']['FabricEvent'];

export const BUS_EVENTS_REFRESH_MS = 10_000;

function apiError(e: unknown) {
  return e instanceof OneMindError ? new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason) : e;
}

const WHAT: Record<string, { label: string; tone: 'ok' | 'warn' | 'neutral' }> = {
  'fabric.connect': { label: 'Connected', tone: 'ok' },
  'fabric.disconnect': { label: 'Disconnected', tone: 'neutral' },
  'fabric.auth_failed': { label: 'Refused', tone: 'warn' },
};

const CAUSE: Record<string, string> = {
  unknown_key: 'A key this box never issued',
  revoked_key: 'A removed key still trying',
  known_key: 'A known key, refused',
};

const who = (e: BusEvent) => e.identity ?? (e.key ? `${e.key.slice(0, 8)}…` : 'No key');

const COLUMNS: Column<BusEvent>[] = [
  { key: 'time', header: 'Time', render: (e) => <time dateTime={e.ts}>{new Date(e.ts).toLocaleString()}</time>, sortValue: (e) => e.seq },
  { key: 'what', header: 'What', render: (e) => <StatusPill tone={WHAT[e.event]?.tone ?? 'neutral'} label={WHAT[e.event]?.label ?? e.event} />, sortValue: (e) => e.event },
  { key: 'who', header: 'Who', render: (e) => <code>{who(e)}</code>, sortValue: (e) => who(e) },
  {
    key: 'detail',
    header: 'Detail',
    render: (e) => {
      const parts = [e.cause ? (CAUSE[e.cause] ?? e.cause) : '', e.reason ?? '', e.account ? `account ${e.account}` : ''].filter(Boolean);
      return `${parts.join(' · ') || '–'}${e.repeats ? ` (+${e.repeats} more)` : ''}`;
    },
  },
];

export function SettingsBusEvents() {
  const { token, mock } = useSignedIn();
  if (mock) return null;
  return <LiveBusEvents token={token} />;
}

function LiveBusEvents({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const res = usePoll(async () => {
    try {
      return await client.call<BusEvents>({ method: 'GET', path: '/v1/fabric/events?count=20' });
    } catch (e) {
      throw apiError(e);
    }
  }, BUS_EVENTS_REFRESH_MS);
  if (res.error?.status === 403) return null;
  const d = res.data;
  return (
    <Card title="Security events" subtitle="Who connected to the message bus, and who was turned away. Read-only.">
      {!d || !Array.isArray(d.events) ? (
        <p className="om-hint" role="status">{res.error ? 'Could not read the events: the hub did not answer.' : 'Loading…'}</p>
      ) : d.observer === 'off' ? (
        <p className="om-hint" role="status">This box does not watch the bus yet (it has no observer key), so nothing is listed.</p>
      ) : (
        <div className="dash-stack">
          {d.observer === 'connecting' && <p className="om-note om-tone-warn" role="status">The observer is not connected to the bus right now.</p>}
          <Table caption="Newest bus events" columns={COLUMNS} rows={d.events} rowKey={(e) => String(e.seq)} initialSort={{ key: 'time', dir: 'desc' }} empty={<p>No bus events yet.</p>} />
        </div>
      )}
    </Card>
  );
}

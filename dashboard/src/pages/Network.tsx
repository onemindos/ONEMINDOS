// SPDX-License-Identifier: Apache-2.0
// Network (NET-UI-01, #239): this box's interfaces, addresses, gateway, DNS, Wi-Fi signal and what it
// listens on, from GET /v1/network (the gateway asks the host service). The cable address can be changed from
// here (NetworkChange: a request an owner approves, with an automatic revert); Wi-Fi and firewall come later.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type NetworkView } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, Table, type Tone } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { NetworkChange } from './NetworkChange';
import { DomainsCard } from './DomainsCard';
import { FirewallCard } from './NetworkFirewall';
import { Load } from './parts';

type Iface = NetworkView['interfaces'][number];
type Port = NetworkView['ports'][number];

const KIND: Record<Iface['kind'], string> = { ethernet: 'Cable', wifi: 'Wi-Fi', loopback: 'This machine', bridge: 'Bridge', virtual: 'Virtual' };
const SCOPE: Record<Port['scope'], string> = { any: 'Every network', loopback: 'This machine only', address: 'One address' };

function stateTone(s: string): Tone {
  return s === 'up' ? 'ok' : s === 'down' ? 'bad' : 'neutral';
}

export function Network() {
  const { token, person, mock, canDecide } = useSignedIn();
  return mock ? (
    <>
      <PageHeader title="Network" />
      <p role="status">Connect to a real hub to see its network. Demo mode has no network data.</p>
    </>
  ) : canDecide === 'no' ? (
    <OwnerOnly />
  ) : (
    <LiveNetwork key={person} token={token} />
  );
}

function OwnerOnly() {
  return (
    <>
      <PageHeader title="Network" />
      <p className="om-note om-tone-warn" role="status">Only an owner can see the network.</p>
    </>
  );
}

function LiveNetwork({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const view = usePoll(async () => {
    try {
      return await client.network.view();
    } catch (e) {
      if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
      throw e;
    }
  }, 30_000);
  const [virtual, setVirtual] = useState(false);
  if (view.error?.status === 403 && view.data === undefined) return <OwnerOnly />;
  return (
    <div className="dash-stack">
      <PageHeader title="Network" lede="How this box is connected: its addresses, gateway and DNS, Wi-Fi, and what it listens on. Changing a cable address is a request an owner approves; your own domains are below." />
      <Button onClick={() => void view.reload()}>Refresh network</Button>
      <Load res={view} what="Loading the network">
        {(v) => {
          if (!v.available) {
            return (
              <p className="om-note om-tone-warn" role="status">
                {v.message ?? 'The network could not be read.'}
              </p>
            );
          }
          const hidden = v.interfaces.filter((i) => i.kind === 'virtual').length;
          const shown = v.interfaces.filter((i) => virtual || i.kind !== 'virtual');
          const open = v.ports.filter((p) => p.scope === 'any');
          return (
            <>
              <NetworkChange client={client} view={v} onChanged={() => void view.reload()} />
              <Card as="article" title="Connection">
                <dl className="om-facts">
                  <div>
                    <dt>Gateway</dt>
                    <dd>{v.gateways.length === 0 ? 'None (no route out of the home network)' : v.gateways.map((g) => `${g.via} via ${g.interface}`).join(', ')}</dd>
                  </div>
                  <div>
                    <dt>DNS servers</dt>
                    <dd>{v.dns.length === 0 ? 'Not reported' : v.dns.join(', ')}</dd>
                  </div>
                  <div>
                    <dt>Reported at</dt>
                    <dd>{v.at ?? 'Not reported'}</dd>
                  </div>
                </dl>
              </Card>
              <Card as="article" title="Interfaces">
                <Table<Iface>
                  caption="Network interfaces"
                  hideCaption
                  rows={shown}
                  rowKey={(i) => i.name}
                  empty="No interfaces reported."
                  columns={[
                    { key: 'name', header: 'Name', render: (i) => <code>{i.name}</code>, sortValue: (i) => i.name },
                    { key: 'kind', header: 'Type', render: (i) => KIND[i.kind] ?? i.kind },
                    { key: 'state', header: 'State', render: (i) => <StatusPill tone={stateTone(i.state)} label={i.state} /> },
                    { key: 'addresses', header: 'Addresses', render: (i) => (i.addresses.length === 0 ? 'None' : i.addresses.join(', ')) },
                    { key: 'mac', header: 'MAC', secondary: true, render: (i) => i.mac ?? '' },
                    { key: 'wifi', header: 'Wi-Fi signal', secondary: true, render: (i) => (i.wifi ? (i.wifi.signal_dbm == null ? 'Not reported' : `${i.wifi.signal_dbm} dBm`) : '') },
                  ]}
                />
                {hidden > 0 && (
                  <Button size="sm" variant="ghost" onClick={() => setVirtual(!virtual)}>
                    {virtual ? 'Hide virtual interfaces' : `Show ${hidden} virtual interface${hidden === 1 ? '' : 's'} (apps and containers)`}
                  </Button>
                )}
              </Card>
              <Card as="article" title="Open ports">
                <p>
                  {open.length} {open.length === 1 ? 'port is' : 'ports are'} open to every network the box is on. This lists what the box listens on, not what the firewall lets through; the Firewall section below shows that.
                </p>
                <Table<Port>
                  caption="Listening ports"
                  hideCaption
                  rows={v.ports}
                  rowKey={(p) => `${p.proto}/${p.addr}/${p.port}`}
                  empty="Nothing is listening."
                  initialSort={{ key: 'port', dir: 'asc' }}
                  columns={[
                    { key: 'port', header: 'Port', sortValue: (p) => p.port },
                    { key: 'proto', header: 'Protocol', render: (p) => p.proto.toUpperCase() },
                    { key: 'scope', header: 'Reachable from', render: (p) => (p.scope === 'address' ? `${SCOPE[p.scope]} (${p.addr})` : SCOPE[p.scope]) },
                  ]}
                />
              </Card>
              <FirewallCard client={client} />
              {v.dropped > 0 && (
                <p className="om-note om-tone-warn" role="note">
                  {v.dropped} {v.dropped === 1 ? 'entry was' : 'entries were'} left out because the box reported something that did not check out.
                </p>
              )}
              <p className="om-hint">Joining Wi-Fi comes next, as a request you approve, with the same automatic revert.</p>
            </>
          );
        }}
      </Load>
      <DomainsCard token={token} />
    </div>
  );
}

// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

// Addresses are RFC 5737 / RFC 3849 documentation ranges; the MAC is in the documentation range of RFC 7042.
const view = {
  available: true, reason: null, message: null, at: '2026-11-20T12:00:00Z', dropped: 0,
  interfaces: [
    { name: 'eth0', kind: 'ethernet', state: 'up', mac: '00:00:5e:00:53:01', mtu: 1500, addresses: ['192.0.2.10/24', '2001:db8::10/64'], wifi: null },
    { name: 'wlan0', kind: 'wifi', state: 'down', mac: '00:00:5e:00:53:02', mtu: 1500, addresses: [], wifi: { signal_dbm: -61 } },
    { name: 'cni0', kind: 'bridge', state: 'up', mac: null, mtu: 1450, addresses: ['198.51.100.1/24'], wifi: null },
    { name: 'veth1234', kind: 'virtual', state: 'up', mac: null, mtu: 1450, addresses: [], wifi: null },
  ],
  gateways: [{ interface: 'eth0', via: '192.0.2.1', family: 'ipv4' }],
  dns: ['192.0.2.53'],
  ports: [
    { proto: 'tcp', addr: '0.0.0.0', port: 22, scope: 'any' },
    { proto: 'tcp', addr: '127.0.0.1', port: 8080, scope: 'loopback' },
    { proto: 'tcp', addr: '192.0.2.10', port: 443, scope: 'address' },
  ],
};
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(answer: () => Response, token = 'owner-demo') {
  const fetch = vi.fn(async (url: string | URL | Request) => {
    const path = new URL(String(url)).pathname;
    expect(['/v1/network', '/v1/domains']).toContain(path); // the screen reads only these two routes
    if (path === '/v1/domains') return response({ enabled: false, acme: { account_thumbprint: null, issuance: 'not_available_yet' }, domains: [] });
    return answer();
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/network']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('shows the gateway, DNS, interfaces and open ports from the gateway, behind the Settings link', async () => {
  const fetch = mount(() => response(view));
  expect(await screen.findByRole('heading', { level: 1, name: 'Network' })).toBeInTheDocument();
  expect(await screen.findByText('192.0.2.1 via eth0')).toBeInTheDocument();
  expect(screen.getByText('192.0.2.53')).toBeInTheDocument();
  const ifaces = within(screen.getByRole('table', { name: 'Network interfaces' }));
  expect(ifaces.getByText('192.0.2.10/24, 2001:db8::10/64')).toBeInTheDocument();
  expect(ifaces.getByText('-61 dBm')).toBeInTheDocument();
  expect(ifaces.getByText('Cable')).toBeInTheDocument();
  expect(ifaces.queryByText('veth1234')).not.toBeInTheDocument(); // virtual interfaces are folded away
  await userEvent.setup().click(screen.getByRole('button', { name: /Show 1 virtual interface/ }));
  expect(ifaces.getByText('veth1234')).toBeInTheDocument();
  const ports = within(screen.getByRole('table', { name: 'Listening ports' }));
  expect(ports.getByText('Every network')).toBeInTheDocument();
  expect(ports.getByText('This machine only')).toBeInTheDocument();
  expect(ports.getByText('One address (192.0.2.10)')).toBeInTheDocument();
  expect(screen.getByText(/1 port is open to every network/)).toBeInTheDocument();
  expect(screen.getByText(/firewall rules are not shown yet/)).toBeInTheDocument();
  // Read only: nothing but GETs, and no control that changes the network.
  expect((fetch.mock.calls as unknown as [unknown, RequestInit | undefined][]).every(([, init]) => (init?.method ?? 'GET') === 'GET')).toBe(true);
  expect(screen.queryByRole('button', { name: /apply|save|set|connect/i })).not.toBeInTheDocument();
});

it('says so when the host service cannot be reached instead of showing an empty network', async () => {
  mount(() => response({ available: false, reason: 'host_service_unreachable', message: 'the host service is not reachable from the gateway, so this box\'s network cannot be read yet', interfaces: [], gateways: [], dns: [], ports: [], dropped: 0 }));
  expect(await screen.findByText(/host service is not reachable/)).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('tells the person when the gateway left entries out because they failed its checks', async () => {
  mount(() => response({ ...view, dropped: 2 }));
  expect(await screen.findByRole('note')).toHaveTextContent('2 entries were left out');
});

it('says who may see it when the gateway refuses', async () => {
  mount(() => response({ error: 'permission_denied', message: 'only an owner may see the box\'s network' }, 403));
  expect(await screen.findByText('Only an owner can see the network.')).toBeInTheDocument();
});

it('tells an adult that only an owner can see the network, without asking the gateway', async () => {
  const fetch = mount(() => response(view), 'adult-demo');
  expect(await screen.findByText('Only an owner can see the network.')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

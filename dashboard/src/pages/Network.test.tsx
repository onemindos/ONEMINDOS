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
// What GET /v1/network/firewall says for the shipped host.nft: documentation addresses only.
const fwView = {
  available: true, reason: null, message: null, at: '2026-11-25T12:00:00Z', dropped: 0, truncated: 0, editable: false,
  exposure: 'lan_and_mesh_only', default_action: 'drop', open_to_anywhere: [],
  headline: 'Blocked by default. Only your home network (LAN), your mesh and this box itself can reach anything. Nothing is open to the internet.',
  sets: [{ name: 'lan4', elements: ['10.0.0.0/8', '192.168.0.0/16'] }, { name: 'lan6', elements: ['fc00::/7', 'fe80::/10'] }],
  chains: [{ name: 'input', base: true, hook: 'input', policy: 'drop', audience: null, rules: 2 }, { name: 'lan', base: false, hook: null, policy: null, audience: 'lan', rules: 1 }],
  rules: [
    { chain: 'input', position: 1, action: 'accept', kind: 'state', audience: 'any_network', proto: null, ports: [], understood: true, summary: 'Replies to connections this box started are always allowed in.' },
    { chain: 'input', position: 2, action: 'jump', kind: 'hand_off', audience: 'lan', proto: null, ports: [], understood: true, summary: "Traffic from devices on your home network (LAN) is checked against the 'lan' list next." },
    { chain: 'lan', position: 1, action: 'accept', kind: 'open_port', audience: 'lan', proto: 'tcp', ports: ['443'], understood: true, summary: 'Devices on your home network (LAN) can reach TCP 443 (the OneMind dashboard and gateway, HTTPS).' },
  ],
  other_tables: [{ family: 'ip', name: 'kube-proxy', chains: 3, rules: 12 }],
};
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(answer: () => Response, token = 'owner-demo', firewall: () => Response = () => response(fwView)) {
  const fetch = vi.fn(async (url: string | URL | Request) => {
    const path = new URL(String(url)).pathname;
    expect(['/v1/network', '/v1/domains', '/v1/network/firewall']).toContain(path); // the screen reads only these routes
    if (path === '/v1/domains') return response({ enabled: false, acme: { account_thumbprint: null, issuance: 'not_available_yet' }, domains: [] });
    return path === '/v1/network/firewall' ? firewall() : answer();
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
  expect(screen.getByText(/the Firewall section below shows that/)).toBeInTheDocument();
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

it('shows the firewall in plain words: what is open, to whom, and that nothing is open to the internet', async () => {
  const fetch = mount(() => response(view));
  expect(await screen.findByRole('heading', { name: 'Firewall' })).toBeInTheDocument();
  expect(await screen.findByText(/Nothing is open to the internet\./)).toBeInTheDocument();
  expect(screen.getByText('Never the internet')).toBeInTheDocument();
  const rules = within(screen.getByRole('table', { name: 'Firewall rules' }));
  expect(rules.getByText('Devices on your home network (LAN) can reach TCP 443 (the OneMind dashboard and gateway, HTTPS).')).toBeInTheDocument();
  expect(rules.getAllByText('Home network (LAN)')).toHaveLength(2);
  expect(rules.getByText('Any address')).toBeInTheDocument();
  expect(screen.getByText(/"Home network" means 10\.0\.0\.0\/8, 192\.168\.0\.0\/16, fc00::\/7, fe80::\/10\./)).toBeInTheDocument();
  expect(screen.getByText(/Other services keep their own rules \(kube-proxy: 12\)/)).toBeInTheDocument();
  expect(screen.queryByText(/Open to any address:/)).not.toBeInTheDocument();
  // Read only: nothing but GETs, and no control that opens a port.
  expect((fetch.mock.calls as unknown as [unknown, RequestInit | undefined][]).every(([, init]) => (init?.method ?? 'GET') === 'GET')).toBe(true);
  expect(screen.queryByRole('button', { name: /allow|open a port|add rule|delete rule/i })).not.toBeInTheDocument();
});

it('warns plainly when a service is open to any address', async () => {
  mount(() => response(view), 'owner-demo', () => response({ ...fwView, exposure: 'open_to_internet', open_to_anywhere: ['tcp/22'], headline: 'Blocked by default. Open to any address, including the internet: tcp/22. Everything else is closed.' }));
  expect(await screen.findByText('Open to the internet')).toBeInTheDocument();
  expect(screen.getByText(/Open to any address: tcp\/22\./)).toBeInTheDocument();
});

it('never says "never the internet" for a firewall it could not fully read', async () => {
  mount(() => response(view), 'owner-demo', () => response({ ...fwView, exposure: 'not_fully_understood', truncated: 3, headline: 'Blocked by default, but this screen could not read everything, so it cannot say nothing is open to the internet: 3 parts of the rules were left out for size.' }));
  expect(await screen.findByText('Not fully checked')).toBeInTheDocument();
  expect(screen.getByText(/cannot say nothing is open to the internet/)).toBeInTheDocument();
  expect(screen.queryByText('Never the internet')).not.toBeInTheDocument();
  expect(screen.getByText(/Part of the rules \(3\) were left out/)).toBeInTheDocument();
});

it('says an unreadable firewall is not a safe one', async () => {
  mount(() => response(view), 'owner-demo', () => response({ available: false, reason: 'host_service_unreachable', message: "the host service is not reachable from the gateway, so this box's firewall cannot be read yet", rules: [], chains: [], sets: [], other_tables: [], dropped: 0, editable: false }));
  expect(await screen.findByText(/firewall cannot be read yet/)).toBeInTheDocument();
  expect(screen.getByText(/not a safe one/)).toBeInTheDocument();
  expect(screen.queryByRole('table', { name: 'Firewall rules' })).not.toBeInTheDocument();
});

it('says "Not protected" when the OneMind firewall is not loaded', async () => {
  mount(() => response(view), 'owner-demo', () => response({ ...fwView, exposure: 'no_firewall', default_action: null, rules: [], chains: [], sets: [], headline: 'The OneMind firewall is not active, or it lets traffic in by default.' }));
  expect(await screen.findByText('Not protected')).toBeInTheDocument();
  expect(screen.getByText('No rules are loaded.')).toBeInTheDocument();
});

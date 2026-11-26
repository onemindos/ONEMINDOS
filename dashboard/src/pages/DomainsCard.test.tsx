// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

function response(value: unknown, code = 200) {
  return new Response(code === 204 ? null : JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });
}

type Dom = { domain: string; verified: boolean; verified_at: string | null; proof: { type: 'TXT'; name: string; value: string }; hosts: unknown[] };
const dom = (domain: string, verified = false, withHost = false): Dom => ({
  domain, verified, verified_at: verified ? '2026-11-25T01:00:00Z' : null,
  proof: { type: 'TXT', name: `_onemind-challenge.${domain}`, value: 'proof-token-123' },
  hosts: withHost ? [{ hostname: `ntfy.${domain}`, app_id: 'ntfy', state: 'requested', requested_by: 'p1', approved_by: null, updated_at: null, public: false }] : [],
});

// A gateway with the domains routes of core/onemind_core/routers/domains.py, over a small in-memory list.
function mount(opts: { enabled?: boolean; domains?: Dom[]; proofFound?: boolean } = {}) {
  const enabled = opts.enabled ?? true;
  const domains = [...(opts.domains ?? [])];
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    if (path === '/v1/network') return response({ available: true, reason: null, message: null, at: null, dropped: 0, interfaces: [], gateways: [], dns: [], ports: [] });
    if (path === '/v1/domains' && method === 'GET') return response({ enabled, acme: { account_thumbprint: null, issuance: 'not_available_yet' }, domains });
    if (path === '/v1/domains' && method === 'POST') {
      const d = dom(String(body.domain).toLowerCase());
      domains.push(d);
      return response(d, 201);
    }
    const check = /^\/v1\/domains\/([^/]+)\/check$/.exec(path);
    if (check && method === 'POST') {
      const d = domains.find((x) => x.domain === check[1])!;
      if (opts.proofFound) d.verified = true;
      return response({ domain: d, proof_found: !!opts.proofFound, addresses: [] });
    }
    const del = /^\/v1\/domains\/([^/]+)$/.exec(path);
    if (del && method === 'DELETE') {
      domains.splice(domains.findIndex((x) => x.domain === del[1]), 1);
      return response(null, 204);
    }
    const ask = /^\/v1\/domains\/([^/]+)\/hosts$/.exec(path);
    if (ask && method === 'POST') {
      const d = domains.find((x) => x.domain === ask[1])!;
      const h = { hostname: `${body.app_id}.${d.domain}`, app_id: body.app_id, state: 'requested', requested_by: 'p1', approved_by: null, updated_at: null, public: false };
      d.hosts.push(h);
      return response(h, 201);
    }
    const hostOp = /^\/v1\/domains\/hosts\/([^/]+)(\/approve)?$/.exec(path);
    if (hostOp) {
      const d = domains.find((x) => (x.hosts as { hostname: string }[]).some((h) => h.hostname === hostOp[1]))!;
      const hosts = d.hosts as { hostname: string; state: string }[];
      const h = hosts.find((x) => x.hostname === hostOp[1])!;
      if (hostOp[2] && method === 'POST') {
        h.state = 'approved';
        return response(h);
      }
      if (!hostOp[2] && method === 'DELETE') {
        hosts.splice(hosts.indexOf(h), 1);
        return response(null, 204);
      }
    }
    return response({ error: 'not_found', message: 'no' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(
    <MemoryRouter initialEntries={['/network']}>
      <SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}>
        <App mock={false} />
      </SessionProvider>
    </MemoryRouter>,
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

it('adds a domain and shows the TXT record to put at the DNS provider', async () => {
  const calls = mount();
  const user = userEvent.setup();
  expect(await screen.findByRole('heading', { name: 'Your own domains' })).toBeInTheDocument();
  expect(await screen.findByText('No domains yet.')).toBeInTheDocument();
  await user.type(screen.getByLabelText('Domain to add'), 'Home.Example.org');
  await user.click(screen.getByRole('button', { name: 'Add domain' }));
  const row = within(await screen.findByRole('region', { name: 'home.example.org' }));
  expect(row.getByText('Not verified yet')).toBeInTheDocument();
  expect(row.getByText('_onemind-challenge.home.example.org')).toBeInTheDocument();
  expect(row.getByText('proof-token-123')).toBeInTheDocument();
  expect(calls.filter((c) => c.method === 'POST').map((c) => [c.path, c.body])).toEqual([['/v1/domains', { domain: 'Home.Example.org' }]]);
});

it('checks the proof record and says when DNS does not have it yet', async () => {
  const calls = mount({ domains: [dom('example.org')] });
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Check example.org' }));
  expect(await screen.findByText(/proof record for example.org was not found yet/)).toBeInTheDocument();
  expect(calls.some((c) => c.method === 'POST' && c.path === '/v1/domains/example.org/check')).toBe(true);
});

it('shows a verified domain with the names asked for under it, and a found record', async () => {
  mount({ domains: [dom('example.org', false, true)], proofFound: true });
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Check example.org' }));
  expect(await screen.findByText('example.org is verified.')).toBeInTheDocument();
  const row = within(screen.getByRole('region', { name: 'example.org' }));
  expect(row.getByText('Verified')).toBeInTheDocument();
  expect(row.getByText('waiting for your approval', { exact: false })).toBeInTheDocument();
  expect(row.queryByText('proof-token-123')).not.toBeInTheDocument();
});

it('asks before removing a domain, and removes it once confirmed', async () => {
  const calls = mount({ domains: [dom('example.org')] });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove example.org' }));
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  await user.click(await screen.findByRole('button', { name: 'Remove domain' }));
  await vi.waitFor(() => expect(screen.getByText('No domains yet.')).toBeInTheDocument());
  expect(calls.filter((c) => c.method === 'DELETE').map((c) => c.path)).toEqual(['/v1/domains/example.org']);
});

it('says the feature is off and offers no way to add while the box has it off', async () => {
  mount({ enabled: false });
  expect(await screen.findByText(/Your own domain is off on this box/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add domain' })).toBeDisabled();
  expect(screen.getByLabelText('Domain to add')).toBeDisabled();
});

it('approves a name only after its full name is typed, then shows it as approved', async () => {
  const calls = mount({ domains: [dom('example.org', true, true)] });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Approve ntfy.example.org' }));
  const approve = screen.getByRole('button', { name: 'Approve name' });
  expect(approve).toBeDisabled();
  await user.type(screen.getByLabelText(/^Type ntfy.example.org to confirm/), 'ntfy.example');
  expect(approve).toBeDisabled();
  await user.type(screen.getByLabelText(/^Type ntfy.example.org to confirm/), '.org');
  await user.click(approve);
  await vi.waitFor(() => expect(screen.getByText(/approved \(not served yet\)/)).toBeInTheDocument());
  expect(calls.filter((c) => c.method === 'POST' && c.path.endsWith('/approve')).map((c) => [c.path, c.body])).toEqual([['/v1/domains/hosts/ntfy.example.org/approve', { confirm: 'ntfy.example.org' }]]);
});

it('asks for a name under a verified domain and removes a name', async () => {
  const calls = mount({ domains: [dom('example.org', true, true)] });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('App to give a name under example.org'), 'kuma');
  await user.click(screen.getByRole('button', { name: 'Ask for this name' }));
  await screen.findByText('kuma.example.org');
  expect(calls.some((c) => c.method === 'POST' && c.path === '/v1/domains/example.org/hosts' && JSON.stringify(c.body) === '{"app_id":"kuma"}')).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Remove the name ntfy.example.org' }));
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false); // nothing happens before the confirmation
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Keep it' }));
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Remove the name ntfy.example.org' }));
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove name' }));
  await vi.waitFor(() => expect(screen.queryByText('ntfy.example.org')).not.toBeInTheDocument());
  expect(calls.some((c) => c.method === 'DELETE' && c.path === '/v1/domains/hosts/ntfy.example.org')).toBe(true);
});

it('offers no name request for a domain that is not verified', async () => {
  mount({ domains: [dom('example.org')] });
  await screen.findByRole('button', { name: 'Check example.org' });
  expect(screen.queryByLabelText('App to give a name under example.org')).not.toBeInTheDocument();
});

it('accepts the confirmation in any case and with spaces around it, as the gateway does', async () => {
  const calls = mount({ domains: [dom('example.org', true, true)] });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Approve ntfy.example.org' }));
  await user.type(screen.getByLabelText(/^Type ntfy.example.org to confirm/), ' NTFY.Example.ORG ');
  await user.click(screen.getByRole('button', { name: 'Approve name' }));
  await vi.waitFor(() => expect(calls.filter((c) => c.path.endsWith('/approve')).map((c) => c.body)).toEqual([{ confirm: 'NTFY.Example.ORG' }]));
});

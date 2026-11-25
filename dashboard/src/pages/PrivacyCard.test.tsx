// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

function response(value: unknown, code = 200) {
  return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });
}

// The gateway answers /v1/mesh and /v1/domains; everything else About asks for is a 404 the page copes with.
function mount(opts: { mode?: string; domainsOn?: boolean; token?: string }) {
  const token = opts.token ?? 'owner-demo';
  const paths: string[] = [];
  const fetch = vi.fn(async (url: string | URL | Request) => {
    const path = new URL(String(url)).pathname;
    paths.push(path);
    if (path === '/v1/mesh') return response({ mode: opts.mode ?? 'lan', box: 'box', control: { state: 'up', checked_at: null }, relay: null, nodes: [], devices: [], names: { lan: [], mesh: [] }, apps: [], https: true, ca_sha256: '' });
    if (path === '/v1/domains') return response({ enabled: !!opts.domainsOn, acme: { account_thumbprint: null, issuance: 'not_available_yet' }, domains: [] });
    return response({ error: 'not_found', message: 'no' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(
    <MemoryRouter initialEntries={['/settings/about']}>
      <SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}>
        <App mock={false} />
      </SessionProvider>
    </MemoryRouter>,
  );
  return paths;
}
afterEach(() => vi.unstubAllGlobals());

it('lists what leaves the box, reading remote access and your own domain from the box', async () => {
  mount({ mode: 'relay', domainsOn: true });
  expect(await screen.findByRole('heading', { name: 'What leaves this box' })).toBeInTheDocument();
  expect(screen.getByText(/no analytics, no crash reporting and no usage statistics/)).toBeInTheDocument();
  expect(screen.getByText(/plain download request \(GET\)/)).toBeInTheDocument();
  expect(await screen.findByText(/passes through your own relay server/)).toBeInTheDocument();
  expect(await screen.findByText(/asks a public DNS server whether your proof record exists/)).toBeInTheDocument();
});

it('says nothing leaves when the mesh is off and your own domain is off', async () => {
  mount({ mode: 'off', domainsOn: false });
  expect(await screen.findByText(/runs without the private mesh/)).toBeInTheDocument();
  expect(await screen.findByText(/The box makes no lookups for your own domain/)).toBeInTheDocument();
});

it('warns about a hosted coordinator when the mesh uses one', async () => {
  mount({ mode: 'hosted' });
  expect(await screen.findByText(/third-party coordination service \(Tailscale\)/)).toBeInTheDocument();
});

it('does not ask the gateway for the owner-only lines for an adult', async () => {
  const paths = mount({ token: 'adult-demo' });
  expect(await screen.findByText(/Only the owner can see how this box is reached from outside/)).toBeInTheDocument();
  expect(paths).not.toContain('/v1/mesh');
  expect(paths).not.toContain('/v1/domains');
});

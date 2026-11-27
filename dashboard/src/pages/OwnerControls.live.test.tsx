// SPDX-License-Identifier: Apache-2.0
// Owner-only controls mounted the way main.tsx mounts them for a real hub: no knownPrincipal, so the session has
// no principal and the role comes only from GET /v1/me (#1284, as #1246 did for Verification levels). The
// gateway still enforces every route; these tests prove the controls are offered to the right roles.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const CA = 'ab'.repeat(32);
const T = { timeout: 5000 };
const ME: Record<string, { id: string; role: string }> = {
  'owner-demo': { id: 'zed', role: 'owner' }, 'adult-demo': { id: 'alex', role: 'adult' }, 'child-demo': { id: 'kai', role: 'child' },
};
const machine = { name: 'db', node_id: 'hub-1', ram_mb: 2048, cpus: 2, disk_gb: 20, state: 'needs_media', created_at: '2026-11-18T00:00:00Z', updated_at: '2026-11-18T00:00:00Z' };
const caps = {
  image_catalogue: [{ name: 'Linux test image', url: 'https://example.test/img.qcow2', sha256: 'a'.repeat(64) }], enabled: true,
  extension: { state: 'ready', message: 'Machines are on.' }, requirements: { min_memory_mb: 8192, arch: 'amd64', kvm: true },
  eligible_node_ids: ['hub-1'], nodes: [{ node_id: 'hub-1', eligible: true, reasons: [] }],
};
const mesh = { mode: 'lan', box: 'testbox', control: { state: 'up', checked_at: null }, relay: null,
  nodes: [{ node_id: 'hub-1', name: 'testbox', role: 'hub', online: true, state: 'up', path: 'none' }], devices: [],
  names: { lan: ['testbox.local'], mesh: [] }, apps: [], https: true, ca_sha256: CA };

function mount(token: string, route: string) {
  const fetchFn = vi.fn(async (url: string | URL | Request) => {
    const p = new URL(String(url), window.location.origin).pathname;
    const me = ME[token]!;
    if (p === '/v1/me') return Response.json({ principal: { id: me.id, kind: 'person', role: me.role }, token: null, session: null, passkeys: 0, scopes: me.role === 'owner' ? ['*'] : ['actions:request'], capabilities: me.role === 'owner' ? ['can_approve', 'can_request'] : ['can_request'], step_up: { passkeys_active: false, require_passkey_approval: false } });
    if (p === '/v1/agents/kill-switch') return Response.json({ on: false, changed_by: null, changed_at: null, reason: null });
    if (p === '/v1/files/app-passwords') return Response.json({ app_passwords: [] });
    if (p === '/v1/machines') return Response.json([machine]);
    if (p === '/v1/machines/capabilities') return Response.json(caps);
    if (p === '/v1/mesh') return Response.json(mesh);
    if (p === '/v1/fabric') return Response.json({ hub_node_id: 'hub-1', counts: {}, nodes: [], joining: [] });
    if (p === '/v1/tls') return Response.json({ ca_sha256: CA, names: ['testbox.local'], not_after: null, https: true, acme: null });
    return Response.json({ error: 'not_found', message: 'No route in test fixture' }, { status: 404 });
  });
  vi.stubGlobal('fetch', fetchFn);
  const http = new HttpApi({ token, fetchFn });
  const api = Object.assign(new MockApi(token), {
    me: http.me.bind(http), machines: http.machines.bind(http), machineSnapshots: http.machineSnapshots.bind(http), machineCapabilities: http.machineCapabilities.bind(http),
    meshView: http.meshView.bind(http), fabricSummary: http.fabricSummary.bind(http), tlsInfo: http.tlsInfo.bind(http), createJoinTicket: http.createJoinTicket.bind(http), caCertUrl: http.caCertUrl.bind(http),
  });
  window.sessionStorage.setItem('onemind.token', token);
  // No knownPrincipal: this is what a real hub gets.
  render(<MemoryRouter initialEntries={[route]}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => undefined }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

// A child is never offered the Pro screens (agents, add-machine, machines), so adult is the non-owner there; the
// child case is covered where the card is reachable (app passwords).
describe('owner controls on a real hub (no knownPrincipal)', () => {
  it.each([['owner-demo', true], ['adult-demo', false]] as const)('agent kill switch button for %s: %s', async (token, shown) => {
    mount(token, '/settings/agents');
    const card = await screen.findByRole('article', { name: 'Agent kill switch' }, T);
    expect(await within(card).findByText('Agents running', undefined, T)).toBeVisible();
    if (shown) expect(await within(card).findByRole('button', { name: 'Stop all AI agents' }, T)).toBeVisible();
    else expect(await within(card).findByText('Only the owner can stop or resume agents.', undefined, T)).toBeVisible();
    expect(within(card).queryByRole('button', { name: 'Stop all AI agents' }) !== null).toBe(shown);
  });

  it.each([['owner-demo', true], ['adult-demo', false]] as const)('Add a device button for %s: %s', async (token, shown) => {
    mount(token, '/add-machine');
    if (shown) expect(await screen.findByRole('button', { name: /Add a device/ }, T)).toBeVisible();
    else expect(await screen.findByText(/Only an owner can make a join code/, undefined, T)).toBeVisible();
    expect(screen.queryByRole('button', { name: /Add a device/ }) !== null).toBe(shown);
  });

  it.each([['owner-demo', true], ['adult-demo', false]] as const)('Transfer media button for %s: %s', async (token, shown) => {
    mount(token, '/machines');
    expect(await screen.findByRole('list', { name: 'Machines' }, T)).toBeVisible();
    if (shown) expect(await screen.findByRole('button', { name: 'Transfer media' }, T)).toBeVisible();
    else expect(await screen.findByRole('button', { name: 'Request removal of db' }, T)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Transfer media' }) !== null).toBe(shown);
  });

  it.each([['owner-demo', true], ['adult-demo', false]] as const)('own installer ISO choice in the create form for %s: enabled %s', async (token, enabled) => {
    mount(token, '/machines');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Request a machine' }, T));
    const option = await screen.findByRole('option', { name: 'My installer ISO' }, T);
    if (enabled) expect(option).toBeEnabled();
    else expect(option).toBeDisabled();
  });

  it.each([['owner-demo', true], ['adult-demo', true], ['child-demo', false]] as const)('app passwords card for %s: %s', async (token, shown) => {
    mount(token, '/settings/account');
    if (shown) expect(await screen.findByText('No app passwords yet.', undefined, T)).toBeVisible();
    else {
      expect(await screen.findByText(/\bkai\b/, undefined, T)).toBeVisible();
      expect(screen.queryByText('No app passwords yet.')).toBeNull();
    }
  });
});

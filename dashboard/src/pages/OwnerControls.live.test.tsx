// SPDX-License-Identifier: Apache-2.0
// Owner-only controls mounted the way main.tsx mounts them for a real hub: no knownPrincipal, so the session has
// no principal and the role comes only from GET /v1/me (#1284, as #1246 did for Verification levels). The
// gateway still enforces every route; these tests prove the controls are offered to the right roles.
import { render, screen, waitFor, within } from '@testing-library/react';
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

function mount(token: string, route: string, extra?: (p: string, init?: RequestInit) => Response | undefined) {
  const fetchFn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const p = new URL(String(url), window.location.origin).pathname;
    const other = extra?.(p, init);
    if (other) return other;
    const me = ME[token]!;
    if (p === '/v1/me') return Response.json({ principal: { id: me.id, kind: 'person', role: me.role }, token: null, session: null, passkeys: 0, scopes: me.role === 'owner' ? ['*'] : ['actions:request'], capabilities: me.role === 'owner' ? ['can_approve', 'can_request'] : ['can_request'], step_up: { passkeys_active: false, require_passkey_approval: false } });
    if (p === '/v1/agents/kill-switch') return Response.json({ on: false, changed_by: null, changed_at: null, reason: null });
    if (p === '/v1/files/app-passwords') return Response.json({ app_passwords: [] });
    if (p === '/v1/machines') return Response.json([machine]);
    if (p === '/v1/machines/capabilities') return Response.json(caps);
    if (p === '/v1/mesh') return Response.json(mesh);
    if (p === '/v1/fabric') return Response.json({ hub_node_id: 'hub-1', counts: {}, nodes: [], joining: [] });
    if (p === '/v1/os/fleet') return Response.json({ machines: [], versions: [], active_rollout_id: null });
    if (p === '/v1/os/rollouts') return Response.json([{ id: 'rol_aaaaaaaaaaaaaaaaaaaaaaaaaa', version: '1.3.0', state: 'paused', stage: 0, stages: [10, 100], counts: {} }]);
    if (p === '/v1/os/updates') return Response.json({ nodes: [], install: { available: false } });
    if (p === '/v1/os/updates/history') return Response.json({ events: [], requests: [] });
    if (p === '/v1/windows') return Response.json([{ id: 'win_night', name: 'Night', tz: 'box', open_now: false, ranges: [{ days: ['mon'], start: '22:00', end: '06:00' }] }]);
    if (p === '/v1/radios') return Response.json([{ id: 'rad_1', kind: 'lora', model: 'T-Beam', hostname: 'testbox', node_id: 'hub-1', node_status: 'online', confirm: { confirmed: false, profile: 'meshcore-companion-usb', label: 'MeshCore companion (USB)' } }]);
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
      // Wait until the shell has resolved the role, then prove the card never asked the gateway for app passwords.
      await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).endsWith('/v1/me'))).toBe(true), T);
      await new Promise((r) => setTimeout(r, 300));
      expect(screen.queryByText('No app passwords yet.')).toBeNull();
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/v1/files/app-passwords'))).toBe(false);
    }
  });

  it.each([['owner-demo', true], ['adult-demo', false]] as const)('rollout controls for %s: %s', async (token, shown) => {
    mount(token, '/updates');
    const fleet = await screen.findByRole('region', { name: 'Fleet' }, T);
    expect(await within(fleet).findByText(/Paused: needs a decision/, undefined, T)).toBeVisible();
    await waitFor(() => expect(within(fleet).queryByRole('button', { name: 'Ask to resume' }) !== null).toBe(shown), T);
    expect(within(fleet).queryByRole('button', { name: 'Cancel rollout' }) !== null).toBe(shown);
    expect(within(fleet).queryByRole('button', { name: 'Ask to start a rollout' }) !== null).toBe(false); // a paused rollout is active
  });

  it.each([['owner-demo', true], ['adult-demo', false]] as const)('maintenance window buttons for %s: %s', async (token, shown) => {
    mount(token, '/automation');
    const card = await screen.findByRole('region', { name: 'Maintenance windows' }, T);
    expect(await within(card).findByText('Night', undefined, T)).toBeVisible();
    if (shown) {
      expect(await within(card).findByRole('button', { name: 'Add a window' }, T)).toBeVisible();
      expect(within(card).getByRole('button', { name: 'Edit Night' })).toBeVisible();
      expect(within(card).queryByText('Only an owner can change a window.')).toBeNull();
    } else {
      expect(await within(card).findByText('Only an owner can change a window.', undefined, T)).toBeVisible();
      expect(within(card).queryByRole('button', { name: 'Add a window' })).toBeNull();
      expect(within(card).queryByRole('button', { name: 'Edit Night' })).toBeNull();
    }
  });

  it.each([['owner-demo', true], ['adult-demo', false]] as const)('Confirm what this is for %s: %s', async (token, shown) => {
    mount(token, '/nodes');
    const card = await screen.findByRole('region', { name: 'Radios' }, T);
    expect(await within(card).findByText(/Not confirmed yet/, undefined, T)).toBeVisible();
    if (shown) expect(await within(card).findByRole('button', { name: 'Confirm what this is' }, T)).toBeVisible();
    else expect(await within(card).findByText(/Only an owner can confirm what a radio is\./, undefined, T)).toBeVisible();
    expect(within(card).queryByRole('button', { name: 'Confirm what this is' }) !== null).toBe(shown);
  });

  it('uploads an own ISO to the signed-in person home when there is no knownPrincipal', async () => {
    const metadata: string[] = [];
    const rows = new Map<string, { id: string; length: number; sha256: string }>();
    mount('owner-demo', '/machines', (p, init) => {
      if (init?.method === 'POST' && p === '/v1/files/uploads') {
        metadata.push(new Headers(init.headers).get('Upload-Metadata') ?? '');
        const id = 'upl_' + '1'.padStart(26, '0');
        rows.set(p + '/' + id, { id, length: Number(new Headers(init.headers).get('Upload-Length')), sha256: '1'.repeat(64) });
        return new Response(null, { status: 201, headers: { Location: p + '/' + id } });
      }
      const row = rows.get(p);
      if (row && init?.method === 'PATCH') return new Response(null, { status: 204, headers: { 'Upload-Offset': String(row.length) } });
      if (row && init?.method === 'GET') return Response.json({ ...row, state: 'done' });
      return undefined;
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Request a machine' }, T));
    const form = within(await screen.findByRole('dialog', undefined, T));
    await waitFor(() => expect(form.getByRole('option', { name: 'My installer ISO' })).toBeEnabled(), T);
    await user.selectOptions(form.getByLabelText('Image source'), 'iso');
    await user.upload(form.getByLabelText('Installer ISO'), new File([new Uint8Array(1024)], 'installer.iso'));
    await form.findByText('1'.repeat(64), undefined, T);
    expect(metadata).toHaveLength(1);
    expect(metadata[0]).toContain(btoa('home:zed'));
    expect(metadata[0]).not.toContain(btoa('home:undefined'));
  });
});

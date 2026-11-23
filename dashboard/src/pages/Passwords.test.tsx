// SPDX-License-Identifier: Apache-2.0
// Passwords (#679): the setup page for the built-in Vaultwarden. Pairing needs a signed-in person, the
// QR holds the server address only (never a token), only home-network and mesh addresses are shown,
// and a switched-off Passwords says its vault is kept.
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import type { MeshView } from '@onemind/ui';
import { App } from '../App';
import type { SystemAppRow } from '../api/client';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { passwordAddresses } from './Passwords';

const T = { timeout: 4000 };
const row = (over: Partial<SystemAppRow> = {}): SystemAppRow => ({
  id: 'vaultwarden', name: 'Vaultwarden', kind: 'container', update: 'own', disable: 'allowed', enabled: true,
  can_disable: true, status: 'installed', version: '1.37.5', license: 'AGPL-3.0', update_channel: 'stable',
  disabled_at: null, action_id: null, ...over,
});
const MESH: MeshView = {
  mode: 'lan', box: 'box1', control: { state: 'up', checked_at: null }, relay: null, nodes: [], devices: [],
  names: { lan: ['onemind.local', 'box1.local'], mesh: ['hub.onemind.internal'] },
  apps: [
    { app_id: 'ntfy', lan: 'https://ntfy.box1.local', lan_alias: 'https://ntfy.onemind.local', mesh: 'https://ntfy.apps.onemind.internal' },
    { app_id: 'vaultwarden', lan: 'https://vaultwarden.box1.local', lan_alias: 'https://vaultwarden.onemind.local', mesh: 'https://vaultwarden.apps.onemind.internal' },
  ],
  https: true, ca_sha256: 'ab'.repeat(32),
};

function mount(token: string, rows: SystemAppRow[], mesh: MeshView = MESH) {
  const systemApps = vi.fn(async () => rows);
  const meshView = vi.fn(async () => mesh);
  window.sessionStorage.setItem('onemind.token', token);
  const makeApi = (t: string) => Object.assign(new MockApi(t), { systemApps, meshView });
  render(<MemoryRouter initialEntries={['/passwords']}><SessionProvider deps={{ mock: false, makeApi, knownPrincipal: (t) => DEMO_TOKENS[t] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { systemApps, meshView };
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

it('shows the server address as a QR with the Bitwarden steps, and never puts a token in it', async () => {
  mount('adult-demo', [row()]);
  expect(await screen.findByRole('heading', { level: 1, name: 'Passwords' }, T)).toBeInTheDocument();
  const qr = await screen.findByRole('img', { name: /QR code with the Passwords server address/ }, T);
  expect(qr).toHaveAccessibleName('QR code with the Passwords server address https://vaultwarden.box1.local');
  expect(screen.getByText('https://vaultwarden.apps.onemind.internal')).toBeInTheDocument();
  const steps = screen.getByRole('list', { name: 'Bitwarden app steps' });
  expect(within(steps).getByText(/Self-hosted/)).toBeInTheDocument();
  expect(within(steps).getByText(/master password only you know/)).toBeInTheDocument();
  expect(document.body.textContent).not.toContain('adult-demo');
  expect(qr.outerHTML).not.toContain('adult-demo');
  expect(screen.getByRole('link', { name: 'source code' })).toHaveAttribute('href', 'https://github.com/dani-garcia/vaultwarden');
  expect(screen.getByText(/AGPL-3.0/)).toBeInTheDocument();
  expect(screen.getByRole('note')).toHaveTextContent(/Not working yet/);
});

it('lists only home-network and mesh addresses, and the mesh one only while the mesh is on', () => {
  expect(passwordAddresses(MESH).map((a) => a.url)).toEqual([
    'https://vaultwarden.box1.local', 'https://vaultwarden.onemind.local', 'https://vaultwarden.apps.onemind.internal',
  ]);
  expect(passwordAddresses({ ...MESH, mode: 'off', names: { lan: MESH.names.lan, mesh: [] } }).map((a) => a.label)).toEqual(['At home', 'At home (short name)']);
  expect(passwordAddresses({ ...MESH, apps: [] })).toEqual([]);
});

it('says a switched-off Passwords keeps its vault, and shows no address or QR', async () => {
  const { meshView } = mount('owner-demo', [row({ enabled: false, status: 'stopped', disabled_at: '2026-11-22T10:00:00Z' })]);
  expect(await screen.findByRole('heading', { name: 'Passwords is switched off' }, T)).toBeInTheDocument();
  expect(screen.getByText(/Your vault is kept on this box\. Nothing was deleted\./)).toBeInTheDocument();
  expect(screen.queryByRole('img', { name: /QR code/ })).not.toBeInTheDocument();
  expect(screen.queryByText('https://vaultwarden.box1.local')).not.toBeInTheDocument();
  expect(meshView).toHaveBeenCalled(); // read in parallel, but never shown while it is off
});

it('says when Passwords is not installed yet', async () => {
  mount('owner-demo', [row({ status: null })]);
  expect(await screen.findByRole('heading', { name: 'Passwords is not running' }, T)).toBeInTheDocument();
  expect(screen.queryByRole('img', { name: /QR code/ })).not.toBeInTheDocument();
});

it('says when this box’s OS does not list Passwords as built in', async () => {
  mount('owner-demo', [{ ...row(), id: 'photos', kind: 'native' }]);
  expect(await screen.findByText(/does not list Passwords as built in yet/, undefined, T)).toBeInTheDocument();
});

it('refuses an agent: pairing needs a signed-in person, and nothing is read for it', async () => {
  const { systemApps, meshView } = mount('agent-demo', [row()]);
  expect(await screen.findByText(/needs a signed-in person/, undefined, T)).toBeInTheDocument();
  expect(screen.queryByRole('img', { name: /QR code/ })).not.toBeInTheDocument();
  expect(systemApps).not.toHaveBeenCalled();
  expect(meshView).not.toHaveBeenCalled();
});

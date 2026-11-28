// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const node = {
  node_id: 'box0123456789', hostname: 'beelink', status: 'online', reported: true, channel: 'security',
  current_version: '0.1.1', available_version: '0.1.2', state: 'idle', last_check: '2026-11-18T10:00:00Z', last_result: 'update available',
  rauc: { present: true, booted_slot: 'A', slots: [{ name: 'rootfs.0', bootname: 'A', state: 'booted', boot_status: 'good', bundle_version: '0.1.1' }] },
};
const rollback = { available: true, version: '0.1.0', slot: 'B', reason: null, message: null };
const status = { nodes: [node], install: { available: false, reason: 'engine_unreachable', message: 'Install at the box with onemind update apply.' } };
const history = { events: [{ node_id: 'box0123456789', state: 'rolled_back', version: '0.1.1', last_result: 'gate: image-bad 0.1.2', observed_at: '2026-11-17T03:00:00Z' }], requests: [] };
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(route: (method: string, path: string, body: unknown) => Response) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    return route(init?.method ?? 'GET', path, init?.body ? JSON.parse(String(init.body)) : undefined);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/settings/updates']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('shows the running version, slots, the offer and the rollback history from the gateway', async () => {
  mount((_, path) => response(path === '/v1/os/updates' ? status : history));
  expect(await screen.findByRole('heading', { level: 1, name: 'OS updates' })).toBeInTheDocument();
  expect(await screen.findByText('0.1.1')).toBeInTheDocument();
  expect(screen.getByText(/Slot A · booted · good · version 0.1.1/)).toBeInTheDocument();
  expect(screen.getByRole('note')).toHaveTextContent('not available yet');
  expect(await screen.findByText(/Rolled back · version 0.1.1 · gate: image-bad 0.1.2/)).toBeInTheDocument();
});

it('files an os.update.install request for the owner instead of installing', async () => {
  const sent: unknown[] = [];
  const fetch = mount((method, path, body) => {
    if (method === 'POST' && path === '/v1/actions') { sent.push(body); return response({ id: 'act-1', type: 'os.update.install', state: 'awaiting_approval' }, 201); }
    return response(path === '/v1/os/updates' ? status : history);
  });
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Request install of 0.1.2' }));
  expect(await screen.findByText(/Install request act-1: awaiting_approval/)).toBeInTheDocument();
  expect(sent).toEqual([expect.objectContaining({ type: 'os.update.install', params: { node_id: 'box0123456789', version: '0.1.2' } })]);
  const posts = fetch.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST');
  expect(posts.map(([url]) => new URL(String(url)).pathname)).toEqual(['/v1/actions']);
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-1');
});

it('offers no install button when nothing is on offer and says when a node has no update service', async () => {
  mount((_, path) => response(path === '/v1/os/updates' ? { ...status, nodes: [{ ...node, available_version: null }, { node_id: 'pi', reported: false, rauc: { slots: [] } }] } : history));
  expect(await screen.findByText('This machine runs no update service.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Request install/ })).not.toBeInTheDocument();
});

it('shows a refused install request', async () => {
  mount((method, path) => method === 'POST' ? response({ error: 'policy_refused', message: 'Version 0.1.2 is not the update node offers' }, 409)
    : response(path === '/v1/os/updates' ? status : history));
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Request install of 0.1.2' }));
  await waitFor(() => expect(screen.getByText(/Could not file the request/)).toBeInTheDocument());
});

it('reports an invalid status payload honestly', async () => {
  mount((_, path) => response(path === '/v1/os/updates' ? { nodes: 'x' } : history));
  expect(await screen.findByText(/invalid update status/)).toBeInTheDocument();
});

const goBack = { ...status, nodes: [{ ...node, rollback }], rollback: { available: true, reason: null, message: 'An approved rollback runs on this box.' } };

it('names the previous version and files an os.rollback request for the owner, never going back itself', async () => {
  const sent: unknown[] = [];
  const fetch = mount((method, path, body) => {
    if (method === 'POST' && path === '/v1/actions') { sent.push(body); return response({ id: 'act-9', type: 'os.rollback', state: 'awaiting_approval' }, 201); }
    return response(path === '/v1/os/updates' ? goBack : history);
  });
  expect(await screen.findByText('0.1.0 (slot B)')).toBeInTheDocument();
  expect(screen.getByText(/confirms it with a passkey/)).toBeInTheDocument();
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Go back to 0.1.0' }));
  expect(await screen.findByText(/Go-back request act-9: awaiting_approval/)).toBeInTheDocument();
  expect(screen.getByText(/approves it with a passkey/)).toBeInTheDocument();
  expect(sent).toEqual([expect.objectContaining({ type: 'os.rollback', params: { node_id: 'box0123456789', version: '0.1.0' } })]);
  const posts = fetch.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST');
  expect(posts.map(([url]) => new URL(String(url)).pathname)).toEqual(['/v1/actions']); // filed, never approved here
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-9');
});

it('offers no way back when the other slot is not known good, and says why', async () => {
  const none = { available: false, version: null, slot: null, reason: 'previous_not_good', message: 'Slot B is not marked good (bad): it did not pass the health gate.' };
  mount((_, path) => response(path === '/v1/os/updates' ? { ...goBack, nodes: [{ ...node, rollback: none }] } : history));
  expect(await screen.findByText(/None\. Slot B is not marked good \(bad\)/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Go back to/ })).not.toBeInTheDocument();
});

it('disables going back while the hub cannot reach the host service', async () => {
  const engine = { available: false, reason: 'engine_unreachable', message: 'At the box, the rescue console shows both slots.' };
  mount((_, path) => response(path === '/v1/os/updates' ? { ...goBack, rollback: engine } : history));
  expect(await screen.findByRole('button', { name: 'Go back to 0.1.0' })).toBeDisabled();
  expect(screen.getAllByRole('note').some((n) => /Going back from the hub is not available yet/.test(n.textContent ?? ''))).toBe(true);
});

it('lists go-back requests in the history', async () => {
  mount((_, path) => response(path === '/v1/os/updates' ? goBack : { ...history, requests: [{ type: 'os.rollback', version: '0.1.0', node_id: 'box0123456789', state: 'succeeded' }] }));
  expect(await screen.findByText(/Go back to 0.1.0 on box0123456789 · succeeded/)).toBeInTheDocument();
});

// REL-02 (#154), Z-02 (founder 2026-11-28): security updates ask first by default; the owner opts in to
// automatic installs or moves the window by filing os.update.settings (PUT /v1/os/settings), never directly.
const settingsNode = { ...node, policy: 'notify', window: '02:00-05:00', settings_source: 'image' };
const settingsStatus = { ...status, nodes: [settingsNode], settings: { available: true, reason: null, message: null } };

it('shows the default update policy and window and files a settings change for the owner', async () => {
  const sent: unknown[] = [];
  const fetch = mount((method, path, body) => {
    if (method === 'PUT' && path === '/v1/os/settings') { sent.push(body); return response({ id: 'act-set', type: 'os.update.settings', state: 'awaiting_approval' }, 202); }
    return response(path === '/v1/os/updates' ? settingsStatus : history);
  });
  expect(await screen.findByText('Ask me first (default)', { selector: 'dd' })).toBeInTheDocument();
  expect(screen.getByText(/installs nothing until you approve it/)).toBeInTheDocument();
  expect(screen.getByText('02:00-05:00')).toBeInTheDocument();
  expect(screen.getByText('OneMind default')).toBeInTheDocument();
  const user = userEvent.setup();
  const request = screen.getByRole('button', { name: 'Request change' });
  expect(request).toBeDisabled(); // nothing changed yet
  await user.selectOptions(screen.getByLabelText('Security updates'), 'auto');
  expect(screen.getByText(/approve this change with your passkey/)).toBeInTheDocument();
  await user.click(request);
  expect(await screen.findByText(/Settings change act-set: awaiting_approval/)).toBeInTheDocument();
  expect(sent).toEqual([{ node_id: 'box0123456789', policy: 'auto', window: '02:00-05:00' }]);
  const writes = fetch.mock.calls.filter(([, init]) => ['POST', 'PUT'].includes((init as RequestInit | undefined)?.method ?? 'GET'));
  expect(writes.map(([url]) => new URL(String(url)).pathname)).toEqual(['/v1/os/settings']);
});

it('warns when a machine does not check for security updates at all', async () => {
  mount((_, path) => response(path === '/v1/os/updates' ? { ...settingsStatus, nodes: [{ ...settingsNode, policy: 'off', settings_source: 'owner' }] } : history));
  expect(await screen.findByText(/does not check for security updates/)).toBeInTheDocument();
  expect(screen.getByText('The owner')).toBeInTheDocument();
});

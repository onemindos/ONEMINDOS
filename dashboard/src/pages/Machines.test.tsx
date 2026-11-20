// SPDX-License-Identifier: Apache-2.0
// Machines screen (MACH-01, #281) through the real HTTP client: the states are the gateway's, and
// every button only files a machine.* request that waits for an owner.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { screensNav } from '../test/helpers';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const row = (name: string, state: string) => ({ name, node_id: 'hub-1', ram_mb: 2048, cpus: 2, disk_gb: 20, state, created_at: '2026-11-18T00:00:00Z', updated_at: '2026-11-18T00:00:00Z' });
const caps = (eligible: boolean) => ({
  enabled: false, extension: { state: 'unavailable', message: 'The machines extension is not part of this version yet.' },
  requirements: { min_memory_mb: 8192, arch: 'amd64', kvm: true }, eligible_node_ids: eligible ? ['hub-1'] : [],
  nodes: [{ node_id: 'hub-1', eligible, reasons: eligible ? [] : [{ code: 'no_kvm', message: 'This node has no KVM.' }] }],
});

function setup(opts: { eligible?: boolean; machines?: unknown[]; failFirst?: boolean } = {}) {
  const writes: Array<Record<string, unknown> & { idempotency_key: string; expires_at: string }> = [];
  const fetchFn = vi.fn(async (path: string, init?: RequestInit) => {
    const p = new URL(path, window.location.origin).pathname;
    if (p === '/v1/machines') return Response.json(opts.machines ?? []);
    if (p === '/v1/machines/capabilities') return Response.json(caps(opts.eligible ?? true));
    if (p === '/v1/actions' && init?.method === 'POST') {
      const body = JSON.parse(init.body as string);
      writes.push(body);
      if (opts.failFirst && writes.length === 1) return Response.json({ error: 'internal', message: 'boom' }, { status: 500 });
      return Response.json({ ...body, id: `req-${writes.length}`, state: 'awaiting_approval', requested_by: { id: 'test-owner', kind: 'person', role: 'owner' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    }
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), {
    machines: http.machines.bind(http), machineCapabilities: http.machineCapabilities.bind(http), createAction: http.createAction.bind(http),
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/machines']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { writes, user: userEvent.setup() };
}

describe('Machines screen', () => {
  it('is in the navigation and shows each state in the gateway words', async () => {
    setup({ machines: [row('web', 'running'), row('db', 'stopped'), row('new', 'creating'), row('lost', 'unknown')] });
    expect((await screensNav(userEvent.setup())).getByRole('link', { name: 'Machines' })).toBeInTheDocument();
    await userEvent.setup().keyboard('{Escape}');
    const list = await screen.findByRole('list', { name: 'Machines' });
    expect(within(list).getByText('Running')).toBeInTheDocument();
    expect(within(list).getByText('Stopped')).toBeInTheDocument();
    expect(within(list).getByText('Creating')).toBeInTheDocument();
    expect(within(list).getByText('Unknown')).toBeInTheDocument();
    expect(within(list).getByText(/may or may not exist/)).toBeInTheDocument();
    // a machine that is still being created cannot be touched; a stopped one cannot be stopped
    expect(screen.getByRole('button', { name: 'Request removal of new' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Request stop of db' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request stop of web' })).toBeEnabled();
  });

  it('files a start as a request and does not change the machine state', async () => {
    const { writes, user } = setup({ machines: [row('db', 'stopped')] });
    await user.click(await screen.findByRole('button', { name: 'Request start of db' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.start', params: { name: 'db' } });
    expect(typeof writes[0]!.idempotency_key).toBe('string');
    expect(Number.isFinite(Date.parse(writes[0]!.expires_at))).toBe(true);
    expect(await screen.findByText(/start: awaiting approval/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request start of db' })).toBeDisabled();
    expect(screen.getByText('Stopped')).toBeInTheDocument();
  });

  it('reuses the idempotency key when a lost answer is retried', async () => {
    const { writes, user } = setup({ machines: [row('db', 'stopped')], failFirst: true });
    await user.click(await screen.findByRole('button', { name: 'Request start of db' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    await user.click(await screen.findByRole('button', { name: 'Request start of db' }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]!.idempotency_key).toBe(writes[0]!.idempotency_key);
  });

  it('asks for the machine name before it files a removal', async () => {
    const { writes, user } = setup({ machines: [row('db', 'stopped')] });
    await user.click(await screen.findByRole('button', { name: 'Request removal of db' }));
    const dialog = await screen.findByRole('alertdialog');
    const send = within(dialog).getByRole('button', { name: 'Send removal request' });
    expect(send).toBeDisabled();
    await user.type(within(dialog).getByLabelText('Machine name'), 'wrong');
    expect(send).toBeDisabled();
    await user.clear(within(dialog).getByLabelText('Machine name'));
    await user.type(within(dialog).getByLabelText('Machine name'), 'db');
    await user.click(send);
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.delete', params: { name: 'db', confirm: 'db' } });
  });

  it('files a create with the chosen size and image', async () => {
    const { writes, user } = setup();
    await user.click(await screen.findByRole('button', { name: 'Request a machine' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name'), 'lab');
    await user.type(within(dialog).getByLabelText(/Cloud image/), 'https://example.test/img.qcow2');
    await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.create', params: { name: 'lab', ram_mb: 2048, cpus: 2, disk_gb: 20, image_url: 'https://example.test/img.qcow2' } });
  });

  it('says why a box cannot run machines and does not offer to create one', async () => {
    setup({ eligible: false });
    expect(await screen.findByText(/cannot run virtual machines yet/)).toHaveTextContent('This node has no KVM.');
    expect(screen.getByRole('button', { name: 'Request a machine' })).toBeDisabled();
  });
});

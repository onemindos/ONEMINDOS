// SPDX-License-Identifier: Apache-2.0
// Machines screen (MACH-01, #281) through the real HTTP client: the states are the gateway's, and
// every button only files a machine.* request that waits for an owner.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { screensNav } from '../test/helpers';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { FilesApi } from '../files/api';
import type { Action } from '../api/types';
import { SessionProvider } from '../session';

const row = (name: string, state: string) => ({ name, node_id: 'hub-1', ram_mb: 2048, cpus: 2, disk_gb: 20, state, created_at: '2026-11-18T00:00:00Z', updated_at: '2026-11-18T00:00:00Z' });
const caps = (eligible: boolean, ext = 'ready') => ({
  image_catalogue: [{ name: 'Linux test image', url: 'https://example.test/img.qcow2', sha256: 'a'.repeat(64) }],
  enabled: ext === 'ready', extension: { state: ext, message: ext === 'ready' ? 'Machines are on.' : 'Machines are off. An owner can turn them on.' },
  requirements: { min_memory_mb: 8192, arch: 'amd64', kvm: true }, eligible_node_ids: eligible ? ['hub-1'] : [],
  nodes: [{ node_id: 'hub-1', eligible, reasons: eligible ? [] : [{ code: 'no_kvm', message: 'This node has no KVM.' }] }],
});
afterEach(() => vi.unstubAllGlobals());

function setup(opts: { eligible?: boolean; machines?: unknown[]; failFirst?: boolean; ext?: string; snapshots?: unknown[]; pendingAction?: Action } = {}) {
  const writes: Array<Record<string, unknown> & { idempotency_key: string; expires_at: string }> = [];
  const fetchFn = vi.fn(async (path: string, init?: RequestInit) => {
    const p = new URL(path, window.location.origin).pathname;
    if (p === '/v1/machines') return Response.json(opts.machines ?? []);
    if (/^\/v1\/machines\/[a-z-]+\/snapshots$/.test(p)) return Response.json(opts.snapshots ?? []);
    if (p === '/v1/machines/capabilities') return Response.json(caps(opts.eligible ?? true, opts.ext));
    if (p === '/v1/actions' && init?.method === 'POST') {
      const body = JSON.parse(init.body as string);
      writes.push(body);
      if (opts.failFirst && writes.length === 1) return Response.json({ error: 'internal', message: 'boom' }, { status: 500 });
      return Response.json({ ...body, id: `req-${writes.length}`, state: 'awaiting_approval', requested_by: { id: 'test-owner', kind: 'person', role: 'owner' }, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    }
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const pending = opts.pendingAction;
  const api = Object.assign(new MockApi('owner-demo'), {
    machines: http.machines.bind(http), machineSnapshots: http.machineSnapshots.bind(http), machineCapabilities: http.machineCapabilities.bind(http), createAction: http.createAction.bind(http),
    ...(pending ? { actions: async () => [pending], action: async () => pending } : {}),
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
    await user.selectOptions(within(dialog).getByLabelText('Cloud image'), 'https://example.test/img.qcow2');
    await user.click(within(dialog).getByRole('button', { name: 'Continue' }));
    await user.click(within(dialog).getByRole('button', { name: 'Continue' }));
    expect(within(dialog).getByLabelText('Isolated')).toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Continue' }));
    expect(writes).toHaveLength(0);
    expect(within(dialog).getByText('a'.repeat(64))).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.create', params: { name: 'lab', ram_mb: 2048, cpus: 2, disk_gb: 20,
      source: { kind: 'catalogue', url: 'https://example.test/img.qcow2', sha256: 'a'.repeat(64) }, network: 'isolated' } });
  });

  it('says why a box cannot run machines and offers no way to turn them on or create one', async () => {
    setup({ eligible: false, ext: 'absent' });
    expect(await screen.findByText(/cannot run virtual machines yet/)).toHaveTextContent('This node has no KVM.');
    expect(screen.getByRole('button', { name: 'Turn on' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Request a machine' })).not.toBeInTheDocument();
  });

  it('files one machines.enable request from Turn on, which waits for an owner', async () => {
    const { writes, user } = setup({ ext: 'absent' });
    expect(screen.queryByRole('button', { name: 'Request a machine' })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Turn on' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machines.enable', params: {} });
    expect(await screen.findByText(/It waits in Approvals/)).toBeInTheDocument();
  });

  it('keeps Turn on off when this gateway has no machines layer', async () => {
    setup({ ext: 'unavailable' });
    expect(await screen.findByRole('button', { name: 'Turn on' })).toBeDisabled();
  });

  it('files restart and force off for a running machine as requests, with no extra parameters', async () => {
    const { writes, user } = setup({ machines: [row('web', 'running')] });
    await user.click(await screen.findByRole('button', { name: 'Request restart of web' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.restart', params: { name: 'web' } });
    expect(await screen.findByText(/restart: awaiting approval/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request force off of web' })).toBeDisabled(); // one request waits per machine
  });

  it('files a snapshot with its name, and a copy of a stopped machine with a new name', async () => {
    const { writes, user } = setup({ machines: [row('db', 'stopped')] });
    expect(screen.queryByRole('button', { name: 'Request restart of db' })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Request snapshot of db' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Snapshot name'), 'before-update');
    await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.snapshot', params: { name: 'db', snapshot: 'before-update' } });
  });

  it('files a copy and refuses a name that is already taken', async () => {
    const { writes, user } = setup({ machines: [row('db', 'stopped'), row('web', 'running')] });
    expect(screen.queryByRole('button', { name: 'Request copy of web' })).not.toBeInTheDocument(); // stop it first
    await user.click(await screen.findByRole('button', { name: 'Request copy of db' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name of the copy'), 'web');
    expect(within(dialog).getByRole('alert')).toHaveTextContent('already exists');
    expect(within(dialog).getByRole('button', { name: 'Send request' })).toBeDisabled();
    await user.clear(within(dialog).getByLabelText('Name of the copy'));
    await user.type(within(dialog).getByLabelText('Name of the copy'), 'db-copy');
    await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'machine.clone', params: { source: 'db', name: 'db-copy' } });
  });

  it('lists snapshots and says plainly when a copy is best effort', async () => {
    const snap = (name: string, consistency: string, note: string) => ({ machine: 'web', name, consistency, note, created_at: '2026-11-21T00:00:00Z' });
    const { user } = setup({ machines: [row('web', 'running')], snapshots: [snap('good', 'quiesced', 'Paused first.'), snap('risky', 'quiesce_failed', 'QuiesceFailed copy.')] });
    await user.click(await screen.findByRole('button', { name: 'Snapshots of web' }));
    const list = await screen.findByRole('list', { name: 'Snapshots' });
    expect(within(list).getByText('Consistent')).toBeInTheDocument();
    expect(within(list).getByText('Best effort')).toBeInTheDocument();
    expect(within(list).getByText('QuiesceFailed copy.')).toBeInTheDocument();
  });
});

it('stages both Windows ISO files, reviews firmware and hashes, and files one request', async () => {
  const calls: string[] = [];
  const rows = new Map<string, { id: string; length: number; sha256: string }>();
  const fetchMedia = vi.fn(async (path: string, init?: RequestInit) => {
    const url = new URL(path, window.location.origin).pathname;
    calls.push(`${init?.method} ${url}`);
    if (init?.method === 'POST' && url === '/v1/files/uploads') {
      const headers = new Headers(init.headers);
      expect(headers.get('Upload-Metadata')).toContain(btoa('home:test-owner'));
      const id = `upl_${String(rows.size + 1).padStart(26, '0')}`;
      const key = `${url}/${id}`;
      rows.set(key, { id, length: Number(headers.get('Upload-Length')), sha256: String(rows.size + 1).repeat(64) });
      return new Response(null, { status: 201, headers: { Location: key } });
    }
    const row = rows.get(url);
    if (row && init?.method === 'PATCH') {
      const offset = Number(new Headers(init.headers).get('Upload-Offset'));
      const bytes = (init.body as Blob).size;
      expect(bytes).toBeLessThanOrEqual(256 * 1024);
      return new Response(null, { status: 204, headers: { 'Upload-Offset': String(offset + bytes) } });
    }
    if (row && init?.method === 'GET') return Response.json({ ...row, state: 'done' });
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal('fetch', fetchMedia);
  const { writes, user } = setup();
  await user.click(await screen.findByRole('button', { name: 'Request a machine' }));
  const form = within(await screen.findByRole('dialog'));
  await user.type(form.getByLabelText('Name'), 'win-test');
  await user.selectOptions(form.getByLabelText('Image source'), 'iso');
  const installer = new File([new Uint8Array(300 * 1024)], 'windows.iso');
  await user.upload(form.getByLabelText('Installer ISO'), installer);
  await form.findByText('1'.repeat(64));
  await user.upload(form.getByLabelText(/VirtIO drivers ISO/), new File(['media'], 'drivers.iso'));
  await form.findByText('2'.repeat(64));
  await user.click(form.getByRole('button', { name: 'Continue' }));
  expect(form.getByLabelText(/Persistent TPM/)).toBeDisabled();
  await user.click(form.getByLabelText(/UEFI firmware/));
  await user.click(form.getByLabelText(/Persistent TPM/));
  await user.click(form.getByRole('button', { name: 'Continue' }));
  await user.click(form.getByLabelText(/Connect to other/));
  await user.click(form.getByRole('button', { name: 'Continue' }));
  expect(form.getByText(/UEFI with Secure Boot · TPM on/)).toBeInTheDocument();
  expect(form.getByText('2'.repeat(64))).toBeInTheDocument();
  expect(calls.filter((call) => call.startsWith('PATCH'))).toHaveLength(3);
  expect(writes).toHaveLength(0);
  await user.click(form.getByRole('button', { name: 'Send request' }));
  await waitFor(() => expect(writes).toHaveLength(1));
  expect(writes[0]).toMatchObject({ type: 'machine.create', params: { firmware: 'uefi', tpm: true, network: 'machine_peers',
    source: { kind: 'iso', size_bytes: 300 * 1024, sha256: '1'.repeat(64), upload_id: [...rows.values()][0]?.id },
    virtio_drivers: { size_bytes: 5, sha256: '2'.repeat(64), upload_id: [...rows.values()][1]?.id } } });
});

it('shows the checked digest after transferring media for an approved machine', async () => {
  const hash = 'b'.repeat(64);
  const transfer = vi.fn(async () => Response.json({ name: 'db', media: [{ volume: 'db-disk', sha256: hash, size_bytes: 4 }] }));
  vi.stubGlobal('fetch', transfer);
  const { user, writes } = setup({ machines: [row('db', 'needs_media')] });
  await user.click(await screen.findByRole('button', { name: 'Transfer media' }));
  expect(await screen.findByText(`db-disk · SHA-256 ${hash}`)).toBeInTheDocument();
  const [url, init] = transfer.mock.calls[0] as unknown as [string, RequestInit];
  expect(new URL(url).pathname).toBe('/v1/machines/db/upload');
  expect(init.method).toBe('POST');
  expect(writes).toHaveLength(0);
});

it('lets a second owner inspect the filed machine parameters before approving', async () => {
  const params = { name: 'bsd-test', ram_mb: 3072, cpus: 3, disk_gb: 60, firmware: 'uefi' as const, tpm: true, network: 'isolated' as const,
    source: { kind: 'iso' as const, sha256: 'b'.repeat(64), size_bytes: 3000, upload_id: 'upl_00000000000000000000000001' },
    virtio_drivers: { sha256: 'c'.repeat(64), size_bytes: 4000, upload_id: 'upl_00000000000000000000000002' } };
  const pending: Action = { id: 'act-machine', type: 'machine.create', params, state: 'awaiting_approval',
    requested_by: { id: 'other-owner', kind: 'person', role: 'owner' }, idempotency_key: 'machine-create', expires_at: new Date(Date.now() + 600_000).toISOString() };
  const { user, writes } = setup({ pendingAction: pending });
  await user.click(await screen.findByRole('link', { name: 'Open in Approvals' }));
  await user.click(await screen.findByText('Technical details'));
  const details = screen.getByText('Technical details').closest('details')!;
  expect(JSON.parse(details.querySelector('pre')!.textContent!)).toEqual({ type: 'machine.create', params });
  expect(screen.getAllByText('other-owner').length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: /^Approve / })).toBeInTheDocument();
  expect(writes).toHaveLength(0);
});

it.each(['PATCH', 'HEAD'])('rejects an impossible %s offset on a staged machine upload', async (method) => {
  const fetchFile = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return new Response(null, { status: 201, headers: { Location: '/v1/files/uploads/upl_1' } });
    if (init?.method === 'PATCH' && method === 'HEAD') throw new TypeError('lost reply');
    return new Response(null, { status: 200, headers: { 'Upload-Offset': method === 'PATCH' ? '8' : 'NaN' } });
  });
  const files = new FilesApi('test-only', fetchFile);
  await expect(files.upload(new File(['four'], 'installer.iso'), 'home:test-owner', '/', () => {})).rejects.toThrow('invalid upload offset');
});

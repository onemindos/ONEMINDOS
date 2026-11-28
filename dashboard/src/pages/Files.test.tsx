// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { seriousViolations } from '../test/helpers';

const roots = [{ root: 'home:owner', kind: 'home', name: 'My files', path: '/', access: 'read-write', writable: true, used_bytes: 2000, quota_bytes: null, free_bytes: 5_000_000 }];
const entries = [
  { name: 'Docs', path: '/Docs', type: 'dir', size: null, mtime: '2026-11-20T10:00:00Z' },
  { name: 'notes.txt', path: '/notes.txt', type: 'file', size: 12, mtime: '2026-11-20T10:00:00Z', mime: 'text/plain' },
];
const request = { id: 'frq_1', type: 'files.grant.create', plan: { summary: 'app photos gets read-only access to shared:/' }, risk: 'write', state: 'awaiting_approval', reason: null, requested_by: { id: 'agent-1', kind: 'agent' }, expires_at: '2026-11-22T10:00:00Z', plan_sha256: 'sha256:abc', deny_reason: null };
type Call = { method: string; path: string; search: URLSearchParams; headers: Headers; body: string };
const json = (v: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json', ...headers } });

function mount(handler: (c: Call) => Response | undefined = () => undefined) {
  const calls: Call[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url), 'http://hub.test');
    const c: Call = { method: init?.method ?? 'GET', path: u.pathname, search: u.searchParams, headers: new Headers(init?.headers), body: typeof init?.body === 'string' ? init.body : '' };
    calls.push(c);
    const custom = handler(c);
    if (custom) return custom;
    if (c.path === '/v1/files/roots') return json(roots);
    if (c.path === '/v1/files/list') return json(c.search.get('path') === '/Docs' ? [] : entries);
    if (c.path === '/v1/files/preview') return json({ mime: 'text/plain', kind: 'text', size: 12, inline_safe: true, text: { excerpt: 'hello notes', truncated: false } });
    if (c.path === '/v1/files/trash') return json([{ id: 'tr_1', trash: 'home', root: 'home:owner', path: '/old.txt', name: 'old.txt', type: 'file', size: 5, trashed_at: '2026-11-19T10:00:00Z', purge_at: '2026-12-19T10:00:00Z' }]);
    if (c.path === '/v1/files/grants') return json([]);
    if (c.path === '/v1/files/requests') return json([request]);
    return json({ error: 'not_found', message: 'no' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/files']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

it('browses real folders from the routes, previews a text file and passes axe', async () => {
  const calls = mount();
  const u = userEvent.setup();
  expect(await screen.findByRole('heading', { level: 1, name: 'Files' })).toBeInTheDocument();
  await u.click(await screen.findByRole('button', { name: 'Preview notes.txt' }));
  expect(await screen.findByText('hello notes')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Open folder Docs' }));
  expect(await screen.findByText('This folder is empty.')).toBeInTheDocument();
  expect(calls.find((c) => c.path === '/v1/files/list' && c.search.get('path') === '/Docs')?.search.get('root')).toBe('home:owner');
  expect(calls.every((c) => c.path.startsWith('/v1/files/'))).toBe(true);
  expect(await seriousViolations(screen.getByRole('main'))).toEqual([]);
});

it('uploads over tus: create, then PATCH from the returned offset', async () => {
  const calls = mount((c) => {
    if (c.path === '/v1/files/uploads' && c.method === 'POST') return new Response('{}', { status: 201, headers: { Location: '/v1/files/uploads/upl_1', 'Upload-Offset': '0' } });
    if (c.path === '/v1/files/uploads/upl_1' && c.method === 'PATCH') return new Response(null, { status: 204, headers: { 'Upload-Offset': '3' } });
  });
  const u = userEvent.setup();
  await u.upload(await screen.findByLabelText('Choose files to upload'), new File(['abc'], 'a b.txt', { type: 'text/plain' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
  const create = calls.find((c) => c.method === 'POST')!;
  expect(create.headers.get('Tus-Resumable')).toBe('1.0.0');
  expect(create.headers.get('Upload-Length')).toBe('3');
  expect(create.headers.get('Upload-Metadata')).toContain(`filename ${btoa('a b.txt')}`);
  expect(create.headers.get('Authorization')).toBe('Bearer owner-demo');
  const patch = calls.find((c) => c.method === 'PATCH')!;
  expect(patch.headers.get('Upload-Offset')).toBe('0');
  expect(patch.headers.get('Content-Type')).toBe('application/offset+octet-stream');
});

it('moves to the trash only after a confirmation, with the exact path', async () => {
  const calls = mount((c) => c.path === '/v1/files/ops' ? json({}) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Move notes.txt to trash' }));
  expect(calls.some((c) => c.path === '/v1/files/ops')).toBe(false);
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Move to trash' }));
  await waitFor(() => expect(calls.find((c) => c.path === '/v1/files/ops')).toBeDefined());
  expect(JSON.parse(calls.find((c) => c.path === '/v1/files/ops')!.body)).toEqual({ op: 'trash', root: 'home:owner', path: '/notes.txt' });
});

it('files a trash-empty request, never an approval, with one idempotency key', async () => {
  const calls = mount((c) => c.path === '/v1/files/trash/empty' ? json({ ...request, id: 'frq_2' }, 202) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Trash' }));
  expect(await screen.findByText('old.txt')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Ask to empty this trash' }));
  expect(screen.getByRole('alertdialog')).toHaveAccessibleDescription(/Retained snapshots may still hold copies/);

  await u.click(screen.getByRole('button', { name: 'File the request' }));
  expect(await screen.findByText(/Request frq_2 filed/)).toBeInTheDocument();
  const sent = calls.find((c) => c.path === '/v1/files/trash/empty')!;
  expect(JSON.parse(sent.body)).toEqual({ trash: 'home', approve: false });
  expect(sent.headers.get('Idempotency-Key')).toBeTruthy();
  expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
});

it('approves exactly the plan it showed and shows a refusal when the plan moved', async () => {
  const calls = mount((c) => c.path.endsWith('/approve') ? json({ error: 'stale_precondition', message: 'the request differs from the one you were shown', reason: 'plan_changed' }, 409) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  await u.click(await screen.findByRole('button', { name: 'Review request frq_1' }));
  expect(within(screen.getByRole('alertdialog')).getByText(/read-only access to shared/)).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Approve this plan' }));
  await waitFor(() => expect(calls.find((c) => c.path === '/v1/files/requests/frq_1/approve')).toBeDefined());
  expect(JSON.parse(calls.find((c) => c.path.endsWith('/approve'))!.body)).toEqual({ plan_sha256: 'sha256:abc' });
  expect(await screen.findByText(/differs from the one you were shown/)).toBeInTheDocument();
});

it('files a grant request with approve=false', async () => {
  const calls = mount((c) => c.path === '/v1/files/grants' && c.method === 'POST' ? json(request, 202) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  await u.click(await screen.findByRole('button', { name: 'Request folder access' }));
  await u.type(screen.getByLabelText('App id'), 'photos');
  await u.click(screen.getByRole('button', { name: 'File the request' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/v1/files/grants')).toBe(true));
  expect(JSON.parse(calls.find((c) => c.method === 'POST')!.body)).toEqual({ subject: { kind: 'app', id: 'photos' }, root: 'home:owner', path: '/', access: 'r', approve: false });
});

it('lets an owner review and approve a request they filed themselves', async () => {
  const own = { ...request, requested_by: { id: 'owner', kind: 'person' } };
  const calls = mount((c) => c.path === '/v1/files/requests' ? json([own]) : c.path.endsWith('/approve') ? json({ ...own, state: 'approved' }) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  expect(await screen.findByRole('button', { name: 'Cancel request frq_1' })).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Review request frq_1' }));
  await u.click(screen.getByRole('button', { name: 'Approve this plan' }));
  await waitFor(() => expect(calls.find((c) => c.path === '/v1/files/requests/frq_1/approve')).toBeDefined());
  expect(JSON.parse(calls.find((c) => c.path.endsWith('/approve'))!.body)).toEqual({ plan_sha256: 'sha256:abc' });
});

it('restores yesterday\'s version as a new file, after a confirmation, and says snapshots are not backups', async () => {
  const version = { version: 'snapper-2-20261121T030000Z', cadence: 'timeline', taken_at: '2026-11-21T03:00:00Z', size: 9, mtime: '2026-11-21T02:10:00Z' };
  const calls = mount((c) => {
    if (c.path === '/v1/files/versions') return json({ root: 'home:owner', path: '/notes.txt', enabled: true, exists: true, versions: [version] });
    if (c.path === '/v1/files/ops') return json({ name: 'notes (version 2026-11-21 03.00 UTC).txt', path: '/notes (version 2026-11-21 03.00 UTC).txt', type: 'file', size: 9, mtime: '2026-11-22T10:00:00Z', root: 'home:owner', restored_from: version.version });
    return undefined;
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Preview notes.txt' }));
  const section = await screen.findByRole('region', { name: 'Previous versions' });
  expect(within(section).getByText(/not a backup/)).toBeInTheDocument();
  expect(within(section).getByRole('link', { name: 'Backups' })).toHaveAttribute('href', '/backups');
  expect(calls.some((c) => c.path === '/v1/files/versions')).toBe(false); // loaded only when asked
  await u.click(within(section).getByRole('button', { name: 'Show previous versions' }));
  const restore = await within(section).findByRole('button', { name: /^Restore the version of / });
  expect(calls.find((c) => c.path === '/v1/files/versions')?.search.get('path')).toBe('/notes.txt');
  await u.click(restore);
  expect(calls.some((c) => c.path === '/v1/files/ops')).toBe(false);
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Restore as a new file' }));
  expect(await screen.findByText(/Restored as \/notes \(version 2026-11-21 03\.00 UTC\)\.txt/)).toBeInTheDocument();
  expect(JSON.parse(calls.find((c) => c.path === '/v1/files/ops')!.body)).toEqual({ op: 'restore_version', root: 'home:owner', path: '/notes.txt', version: 'snapper-2-20261121T030000Z' });
  expect(await seriousViolations(screen.getByRole('main'))).toEqual([]);
});

it('says when versions are off instead of offering a restore', async () => {
  mount((c) => c.path === '/v1/files/versions' ? json({ root: 'home:owner', path: '/notes.txt', enabled: false, exists: true, versions: [] }) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Preview notes.txt' }));
  await u.click(await screen.findByRole('button', { name: 'Show previous versions' }));
  expect(await screen.findByText(/Versions are not turned on/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Restore the version/ })).not.toBeInTheDocument();
});

it('lets an owner see storage per person and save one limit, in bytes, with no limit as null', async () => {
  let rows = [
    { person_id: 'owner', root: 'home:owner', limit_bytes: null, used_bytes: 2000 },
    { person_id: 'kid', root: 'home:kid', limit_bytes: 5_000_000_000, used_bytes: 1_500_000 },
    { person_id: null, root: 'shared', limit_bytes: null, used_bytes: 0 },
  ];
  const calls = mount((c) => {
    if (c.path === '/v1/files/quotas' && c.method === 'GET') return json(rows);
    if (c.path === '/v1/files/quotas/kid' && c.method === 'PUT') {
      const limit = JSON.parse(c.body).limit_bytes as number | null;
      rows = rows.map((r) => (r.person_id === 'kid' ? { ...r, limit_bytes: limit } : r));
      return json(rows[1]);
    }
    return undefined;
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Storage limits' }));
  const list = within(await screen.findByRole('list', { name: 'Storage per person' }));
  expect(list.getByText(/uses 1.5 MB of 5.0 GB/)).toBeInTheDocument();
  expect(list.getByText(/Shared space/)).toBeInTheDocument();
  expect(list.queryByLabelText(/Limit for Shared space/)).not.toBeInTheDocument();
  const kid = list.getByLabelText('Limit for kid in GB (empty for none)');
  await u.clear(kid);
  await u.type(kid, '2');
  await u.click(within(screen.getByRole('form', { name: 'Limit for kid' })).getByRole('button', { name: 'Save limit' }));
  await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').map((c) => [c.path, JSON.parse(c.body)])).toEqual([['/v1/files/quotas/kid', { limit_bytes: 2_000_000_000 }]]));
  await u.clear(screen.getByLabelText('Limit for kid in GB (empty for none)'));
  await u.click(within(screen.getByRole('form', { name: 'Limit for kid' })).getByRole('button', { name: 'Save limit' }));
  await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').map((c) => JSON.parse(c.body).limit_bytes)).toEqual([2_000_000_000, null]));
});

it('refuses a negative or non-numeric limit before sending it', async () => {
  const calls = mount((c) => (c.path === '/v1/files/quotas' ? json([{ person_id: 'kid', root: 'home:kid', limit_bytes: null, used_bytes: 1 }]) : undefined));
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Storage limits' }));
  await u.type(await screen.findByLabelText('Limit for kid in GB (empty for none)'), '-3');
  expect(screen.getByRole('button', { name: 'Save limit' })).toBeDisabled();
  expect(calls.some((c) => c.method === 'PUT')).toBe(false);
});

it('reads and writes limits in decimal GB, the unit the row and the CLI use', async () => {
  const calls = mount((c) => {
    if (c.path === '/v1/files/quotas' && c.method === 'GET') return json([{ person_id: 'kid', root: 'home:kid', limit_bytes: 5_000_000_000, used_bytes: 1 }]);
    if (c.method === 'PUT') return json({ person_id: 'kid', root: 'home:kid', limit_bytes: JSON.parse(c.body).limit_bytes, used_bytes: 1 });
    return undefined;
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Storage limits' }));
  const field = await screen.findByLabelText('Limit for kid in GB (empty for none)');
  expect(field).toHaveValue('5');
  expect(screen.getByText(/of 5.0 GB/)).toBeInTheDocument();
  await u.clear(field);
  await u.type(field, '5');
  await u.click(screen.getByRole('button', { name: 'Save limit' }));
  await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').map((c) => JSON.parse(c.body).limit_bytes)).toEqual([5_000_000_000]));
});

it('refuses a limit of 0, which would block every write, and says why', async () => {
  const calls = mount((c) => (c.path === '/v1/files/quotas' ? json([{ person_id: 'kid', root: 'home:kid', limit_bytes: null, used_bytes: 1 }]) : undefined));
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Storage limits' }));
  await u.type(await screen.findByLabelText('Limit for kid in GB (empty for none)'), '0');
  expect(screen.getByRole('button', { name: 'Save limit' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent(/above 0/);
  await u.click(screen.getByRole('button', { name: 'Save limit' }));
  expect(calls.some((c) => c.method === 'PUT')).toBe(false);
});

it('explains an empty list instead of showing nothing', async () => {
  mount((c) => (c.path === '/v1/files/quotas' ? json([]) : undefined));
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Storage limits' }));
  expect(await screen.findByText(/No person has a home space yet/)).toBeInTheDocument();
});

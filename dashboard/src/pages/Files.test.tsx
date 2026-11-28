// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { MockApi } from '../api/mock';
import * as webauthn from '../lib/webauthn';
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
const createdShare = {
  ...request, id: 'frq_share', type: 'files.shares.create',
  one_time: { token: 'oms_x', path: '/v1/share/oms_x', url: 'https://hub.test/v1/share/oms_x' },
};

function mount(handler: (c: Call) => Response | Promise<Response> | undefined = () => undefined, who = 'owner-demo', meReady?: Promise<void>) {
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
  window.sessionStorage.setItem('onemind.token', who);
  const api = new MockApi(who);
  if (meReady) {
    const me = api.me.bind(api);
    vi.spyOn(api, 'me').mockImplementation(async () => {
      await meReady;
      return me();
    });
  }
  render(<MemoryRouter initialEntries={['/files']}><SessionProvider deps={{ mock: false, makeApi: () => api }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('browses real folders from the routes, previews a text file and passes axe', async () => {
  const calls = mount();
  const u = userEvent.setup();
  expect(await screen.findByRole('heading', { level: 1, name: 'Files' })).toBeInTheDocument();
  await u.click(await screen.findByRole('button', { name: 'Preview notes.txt' }));
  expect(await screen.findByText('hello notes')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Open folder Docs' }));
  expect(await screen.findByText('This folder is empty.')).toBeInTheDocument();
  expect(calls.find((c) => c.path === '/v1/files/list' && c.search.get('path') === '/Docs')?.search.get('root')).toBe('home:owner');
  // Atlas 07: the sidebar and Copies column also read the backup status and (owners) disk health; nothing else, and only reads.
  expect(calls.every((c) => c.path.startsWith('/v1/files/') || (c.method === 'GET' && ['/v1/backups/status', '/v1/backups/runs', '/v1/storage/devices'].includes(c.path)))).toBe(true);
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

it('confirms a file approval with the request-specific sign-in proof', async () => {
  const sign = vi.spyOn(webauthn, 'getPasskey').mockResolvedValue({ id: 'test-credential' });
  const calls = mount((c) => {
    if (c.path === '/v1/actions/frq_1/approve-options') {
      return json({ challenge: 'request-challenge', plan_sha256: request.plan_sha256,
        publicKey: { challenge: 'request-challenge' }, required_level: 'L1' });
    }
    if (c.path === '/v1/files/requests/frq_1/approve') {
      return JSON.parse(c.body).webauthn ? json({ ...request, state: 'succeeded' }) :
        json({ error: 'unauthenticated', reason: 'step_up_required', message: 'Confirm this approval' }, 401);
    }
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  await u.click(await screen.findByRole('button', { name: 'Review request frq_1' }));
  await u.click(screen.getByRole('button', { name: 'Approve this plan' }));
  await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/approve'))).toHaveLength(2));
  expect(sign).toHaveBeenCalledWith({ challenge: 'request-challenge' });
  const final = calls.filter((c) => c.path.endsWith('/approve'))[1]!;
  expect(JSON.parse(final.body)).toEqual({ plan_sha256: request.plan_sha256, webauthn: { id: 'test-credential' } });
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

it('waits for /v1/me before showing the owner Files controls', async () => {
  let resolveMe!: () => void;
  const meReady = new Promise<void>((resolve) => { resolveMe = resolve; });
  const calls = mount(undefined, 'owner-demo', meReady);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  expect(await screen.findByText(/app photos gets read-only access/)).toBeInTheDocument();
  for (const name of ['Trash', 'Storage limits', 'Request folder access', 'Review request frq_1']) {
    expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
  }
  expect(calls.some((c) => c.path === '/v1/files/trash')).toBe(false);

  resolveMe();
  expect(await screen.findByRole('button', { name: 'Request folder access' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Review request frq_1' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Storage limits' })).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Trash' }));
  expect(screen.getByRole('button', { name: 'Shared trash' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Ask to empty this trash' })).toBeInTheDocument();
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

it('sends a file to an app that accepts files: a pointer, keyed once, never the content', async () => {
  const calls = mount((c) => {
    if (c.path === '/v1/share/targets') return json({ type: 'file', targets: [{ app_id: 'photos', name: 'Photos', verbs: ['open', 'add'] }] });
    if (c.path === '/v1/share' && c.method === 'POST') return json({ id: 'evt1', to: 'photos', verb: 'add', object: { type: 'file', ref: 'home:owner:/notes.txt' }, link: 'onemind://photos/file/x', sent_at: '2026-11-26T12:00:00Z' }, 201);
    return undefined;
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Send notes.txt to an app' }));
  expect(calls.find((c) => c.path === '/v1/share/targets')!.search.get('type')).toBe('file');
  const dialog = within(await screen.findByRole('dialog'));
  await u.click(dialog.getByRole('button', { name: 'Add to Photos' }));
  expect(await dialog.findByText(/Sent to Photos\. notes\.txt was added to Photos/)).toBeInTheDocument();
  const post = calls.find((c) => c.path === '/v1/share' && c.method === 'POST')!;
  expect(JSON.parse(post.body)).toEqual({ to: 'photos', verb: 'add', object: { type: 'file', ref: 'home:owner:/notes.txt' } });
  expect(post.headers.get('Idempotency-Key')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Send Docs to an app' })).not.toBeInTheDocument(); // folders are not sent
});

it('says plainly when no app accepts files', async () => {
  mount((c) => (c.path === '/v1/share/targets' ? json({ type: 'file', targets: [] }) : undefined));
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Send notes.txt to an app' }));
  expect(await screen.findByText(/No app on this box accepts files yet/)).toBeInTheDocument();
});

it('shows a retry as the same share: the second press reuses the key', async () => {
  let n = 0;
  const calls = mount((c) => {
    if (c.path === '/v1/share/targets') return json({ type: 'file', targets: [{ app_id: 'photos', name: 'Photos', verbs: ['open'] }] });
    if (c.path === '/v1/share' && c.method === 'POST') return ++n === 1 ? json({ error: 'unavailable', message: 'try later' }, 400) : json({ id: 'evt1', to: 'photos', verb: 'open', object: { type: 'file', ref: 'home:owner:/notes.txt' }, link: 'onemind://photos/file/x', sent_at: '2026-11-26T12:00:00Z' }, 201);
    return undefined;
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Send notes.txt to an app' }));
  const dialog = within(await screen.findByRole('dialog'));
  await u.click(dialog.getByRole('button', { name: 'Open in Photos' }));
  expect(await dialog.findByText(/retries this one share/)).toBeInTheDocument();
  await u.click(dialog.getByRole('button', { name: 'Open in Photos' }));
  expect(await dialog.findByText(/Photos can now open notes\.txt/)).toBeInTheDocument();
  const keys = calls.filter((c) => c.path === '/v1/share' && c.method === 'POST').map((c) => c.headers.get('Idempotency-Key'));
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

it.each(['child-demo', 'guest-demo'])('does not offer Send to as %s: only an owner or an adult sends', async (token) => {
  const calls = mount(() => undefined, token);
  expect(await screen.findByRole('button', { name: 'Download notes.txt' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Send .* to an app$/ })).not.toBeInTheDocument();
  expect(calls.some((c) => c.path.startsWith('/v1/share'))).toBe(false);
});

it('offers Send to as an adult', async () => {
  mount(() => undefined, 'adult-demo');
  expect(await screen.findByRole('button', { name: 'Send notes.txt to an app' })).toBeInTheDocument();
});

it('uses the reviewed Files plan for passkey approval', async () => {
  const pending = { ...createdShare, one_time: undefined };
  const publicKey = { challenge: 'file-challenge' };
  const assertion = { id: 'credential' };
  const sign = vi.spyOn(webauthn, 'getPasskey').mockResolvedValue(assertion);
  const calls = mount((c) => {
    if (c.path === '/v1/files/requests') return json([pending]);
    if (c.path === '/v1/actions/frq_share/approve-options') return json({ plan_sha256: pending.plan_sha256, publicKey });
    if (c.path.endsWith('/approve')) {
      return JSON.parse(c.body).webauthn
        ? json({ ...pending, state: 'succeeded' })
        : json({ error: 'unauthenticated', reason: 'step_up_required', message: 'Use a passkey' }, 401);
    }
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  await u.click(await screen.findByRole('button', { name: 'Review request frq_share' }));
  await u.click(screen.getByRole('button', { name: 'Approve this plan' }));
  const approvals = () => calls.filter((c) => c.path === '/v1/files/requests/frq_share/approve');
  await waitFor(() => expect(approvals()).toHaveLength(2));
  expect(sign).toHaveBeenCalledOnce();
  expect(sign).toHaveBeenCalledWith(publicKey);
  expect(approvals().map((c) => JSON.parse(c.body))).toEqual([
    { plan_sha256: pending.plan_sha256 }, { plan_sha256: pending.plan_sha256, webauthn: assertion },
  ]);
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

it('requests a rename with the new name only, then reloads the folder', async () => {
  const calls = mount((c) => c.path === '/v1/files/ops' ? json({ ...request, id: 'frq_rename', type: 'files.rename' }, 202) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Rename notes.txt' }));
  const dlg = screen.getByRole('dialog');
  const field = within(dlg).getByLabelText('New name');
  expect(field).toHaveValue('notes.txt');
  expect(within(dlg).getByRole('button', { name: 'Request rename' })).toBeDisabled();
  await u.clear(field); await u.type(field, 'a/b');
  expect(within(dlg).getByRole('button', { name: 'Request rename' })).toBeDisabled();
  await u.clear(field); await u.type(field, 'plan.txt');
  const lists = () => calls.filter((c) => c.method === 'GET' && c.path === '/v1/files/list').length;
  const listsBefore = lists();
  await u.click(within(dlg).getByRole('button', { name: 'Request rename' }));
  await waitFor(() => expect(calls.some((c) => c.path === '/v1/files/ops')).toBe(true));
  const op = calls.find((c) => c.path === '/v1/files/ops')!;
  expect(op.method).toBe('POST');
  expect(JSON.parse(op.body)).toEqual({ op: 'rename', root: 'home:owner', path: '/notes.txt', name: 'plan.txt' });
  expect(await screen.findByText(/Rename request frq_rename is waiting for owner approval/)).toBeInTheDocument();
  expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
  await waitFor(() => expect(lists()).toBeGreaterThan(listsBefore));
});

it('requests a share link and shows the secret once, with recipient instructions', async () => {
  const calls = mount((c) => c.path === '/v1/files/shares' && c.method === 'POST'
    ? json(createdShare, 202) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Share link for notes.txt' }));
  expect(screen.queryByRole('button', { name: 'Share link for Docs' })).toBeNull();
  const dlg = screen.getByRole('dialog');
  await u.selectOptions(within(dlg).getByLabelText('Expires after'), '1 day');
  await u.click(within(dlg).getByRole('button', { name: 'Request link' }));
  const url = await within(screen.getByRole('dialog')).findByDisplayValue('https://hub.test/v1/share/oms_x');
  expect(url).toHaveAttribute('readonly');
  expect(screen.getByText(/Request frq_share is waiting for owner approval/)).toBeInTheDocument();
  expect(screen.getByText(/Recipients use an API client.*OneMind-Share-Password/)).toBeInTheDocument();
  expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
  await u.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Copy link' }));
  expect(await navigator.clipboard.readText()).toBe('https://hub.test/v1/share/oms_x');
  const post = calls.find((c) => c.path === '/v1/files/shares' && c.method === 'POST')!;
  const body = JSON.parse(post.body);
  expect(body.items).toEqual([{ root: 'home:owner', path: '/notes.txt' }]);
  expect(body.name).toBe('notes.txt');
  expect(body.password).toBeUndefined();
  const ms = Date.parse(body.expires_at) - Date.now();
  expect(ms).toBeGreaterThan(23 * 3_600_000); expect(ms).toBeLessThan(25 * 3_600_000);
  // the gateway does not replay share creates by key, so none is sent (a retry could make a second link)
  expect(post.headers.get('Idempotency-Key')).toBeNull();
});

it('shares a file whose name exceeds the gateway label limit', async () => {
  const name = 'a'.repeat(121);
  const path = `/${name}`;
  const calls = mount((c) => {
    if (c.path === '/v1/files/list') return json([{ ...entries[1], name, path }]);
    if (c.path === '/v1/files/shares' && c.method === 'POST') {
      const label = (JSON.parse(c.body) as { name?: string }).name;
      if (label !== undefined && [...label].length > 120) return json({ error: 'conflict', message: 'Label too long' }, 422);
      return json(createdShare, 202);
    }
  });
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: `Share link for ${name}` }));
  await u.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Request link' }));
  const post = calls.find((c) => c.path === '/v1/files/shares' && c.method === 'POST')!;
  const body = JSON.parse(post.body);
  expect(body.items).toEqual([{ root: 'home:owner', path }]);
  expect(body.name).toBeUndefined();
  expect(await screen.findByDisplayValue('https://hub.test/v1/share/oms_x')).toBeInTheDocument();
});

it.each(['Escape', 'Close', 'backdrop'])('keeps the pending share open on %s until the URL is shown', async (dismiss) => {
  let release!: (r: Response) => void;
  const slow = new Promise<Response>((res) => { release = res; });
  mount((c) => c.path === '/v1/files/shares' && c.method === 'POST' ? slow : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Share link for notes.txt' }));
  const dlg = screen.getByRole('dialog');
  await u.click(within(dlg).getByRole('button', { name: 'Request link' }));
  if (dismiss === 'Escape') await u.keyboard('{Escape}');
  else if (dismiss === 'Close') await u.click(within(dlg).getByRole('button', { name: 'Close' }));
  else await u.click(dlg.parentElement!);
  expect(dlg).toBeInTheDocument();
  release(json(createdShare, 202));
  expect(await within(dlg).findByDisplayValue('https://hub.test/v1/share/oms_x')).toBeInTheDocument();
  await u.click(within(dlg).getByRole('button', { name: 'Done' }));
  expect(dlg).not.toBeInTheDocument();
});

it('sends one POST when Request link is clicked twice while the first is in flight', async () => {
  let release!: (r: Response) => void;
  const slow = new Promise<Response>((res) => { release = res; });
  const calls = mount((c) => c.path === '/v1/files/shares' && c.method === 'POST' ? slow : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Share link for notes.txt' }));
  const btn = within(screen.getByRole('dialog')).getByRole('button', { name: 'Request link' });
  await u.click(btn);
  await u.click(btn);
  expect(calls.filter((c) => c.path === '/v1/files/shares' && c.method === 'POST')).toHaveLength(1);
  expect(btn).toBeDisabled();
  release(json({ ...createdShare, one_time: { url: 'https://hub.test/v1/share/oms_y' } }, 202));
  await within(screen.getByRole('dialog')).findByDisplayValue('https://hub.test/v1/share/oms_y');
  expect(calls.filter((c) => c.path === '/v1/files/shares' && c.method === 'POST')).toHaveLength(1);
});

it('counts password characters, not UTF-16 units: 4 emoji are too short', async () => {
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Share link for notes.txt' }));
  const dlg = within(screen.getByRole('dialog'));
  await u.type(dlg.getByLabelText(/Password/), '😀😀😀😀');
  expect(dlg.getByRole('button', { name: 'Request link' })).toBeDisabled();
});

it('does not retry a share link create that failed with a server error', async () => {
  const calls = mount((c) => c.path === '/v1/files/shares' && c.method === 'POST' ? json({ error: 'unavailable', message: 'busy' }, 502) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Share link for notes.txt' }));
  await u.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Request link' }));
  await screen.findByRole('alert');
  expect(calls.filter((c) => c.path === '/v1/files/shares' && c.method === 'POST')).toHaveLength(1);
});

it('offers share links only to an owner or an adult', async () => {
  mount(undefined, 'teen-demo');
  await screen.findByRole('button', { name: 'Preview notes.txt' });
  expect(screen.queryByRole('button', { name: /Share link for/ })).toBeNull();
  const u = userEvent.setup();
  await u.click(screen.getByRole('button', { name: 'Sharing' }));
  await screen.findByRole('heading', { name: 'Requests' });
  expect(screen.queryByRole('heading', { name: 'Share links' })).toBeNull();
});

it('lists share links without secrets and requests to end one after a confirmation', async () => {
  const link = { id: 'shl_1', name: 'trip photos', created_by: 'owner', state: 'active', items: [{ kind: 'file' }], password: true, created_at: '2026-11-27T10:00:00Z', expires_at: '2026-12-04T10:00:00Z', opened_count: 3 };
  const calls = mount((c) => c.path === '/v1/files/shares' ? json([link]) : c.path === '/v1/files/shares/shl_1' && c.method === 'DELETE' ? json({ ...request, id: 'frq_end', type: 'files.shares.revoke' }, 202) : undefined);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  expect(await screen.findByText('trip photos')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'End share link trip photos' }));
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Request to end link' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/v1/files/shares/shl_1')).toBe(true));
  const gets = () => calls.filter((c) => c.method === 'GET' && c.path === '/v1/files/shares').length;
  await waitFor(() => expect(gets()).toBeGreaterThan(1));
  expect(await screen.findByText(/Request frq_end filed/)).toBeInTheDocument();
  expect(screen.getByText('active')).toBeInTheDocument();
  expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
});

it('offers a share link for regular files but not symlinks', async () => {
  mount((c) => c.path === '/v1/files/list'
    ? json([...entries, { ...entries[1], name: 'shortcut', path: '/shortcut', type: 'symlink' }]) : undefined);
  expect(await screen.findByRole('button', { name: 'Preview shortcut' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Share link for notes.txt' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Share link for shortcut' })).toBeNull();
});

// #1232: every household role opens Files and sees only what the hub lists for it; only the owner has the owner tabs.
it.each([['adult-demo', 'alex'], ['teen-demo', 'tess'], ['child-demo', 'kai']])('lets %s browse and upload in their own Files, without the owner tabs or a Review button', async (who, id) => {
  const home = { ...roots[0]!, root: `home:${id}` };
  const calls = mount((c) => c.path === '/v1/files/roots' ? json([home]) : undefined, who);
  const u = userEvent.setup();
  expect(await screen.findByRole('button', { name: 'Preview notes.txt' })).toBeInTheDocument();
  expect(screen.queryByText(/not allowed/i)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Upload files' })).toBeInTheDocument();
  expect(calls.find((c) => c.path === '/v1/files/list')?.search.get('root')).toBe(`home:${id}`);
  expect(screen.getByRole('button', { name: 'Trash' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Storage limits' })).not.toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Sharing' }));
  expect(await screen.findByText(/app photos gets read-only access/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Review request frq_1' })).not.toBeInTheDocument();
  // Atlas Files (#1350) shows backup facts to the roles the gateway lets read them: an adult's two GETs, nobody else's.
  const backupReads = who === 'adult-demo' ? ['/v1/backups/status', '/v1/backups/runs'] : [];
  expect(calls.every((c) => c.path.startsWith('/v1/files/') || (c.method === 'GET' && backupReads.includes(c.path)))).toBe(true);
  expect(calls.some((c) => c.path === '/v1/files/quotas')).toBe(false);
});

it('shows a guest only the shared folder, read-only, with no trash of their own', async () => {
  mount((c) => c.path === '/v1/files/roots' ? json([{ root: 'shared', kind: 'shared', name: 'Shared', path: '/', access: 'read', writable: false, used_bytes: 0, quota_bytes: null, free_bytes: null }]) : undefined, 'guest-demo');
  expect(await screen.findByRole('button', { name: 'Preview notes.txt' })).toBeInTheDocument();
  expect(screen.getByText('Read-only here.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Upload files' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Trash' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Storage limits' })).not.toBeInTheDocument();
});


it.each(['adult-demo', 'teen-demo', 'child-demo', 'guest-demo'])('shows only the Files controls allowed for %s', async (who) => {
  mount(undefined, who);
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Sharing' }));
  expect(await screen.findByText(/app photos gets read-only access/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Request folder access' })).not.toBeInTheDocument();
  if (who === 'guest-demo') {
    expect(screen.queryByRole('button', { name: 'Trash' })).not.toBeInTheDocument();
    return;
  }
  await u.click(screen.getByRole('button', { name: 'Trash' }));
  expect(screen.getByRole('button', { name: 'My trash' })).toBeInTheDocument();
  expect(await screen.findByRole('button', { name: 'Restore old.txt' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Ask to empty this trash' })).not.toBeInTheDocument();
  const shared = screen.queryByRole('button', { name: 'Shared trash' });
  if (who === 'adult-demo') {
    expect(shared).toBeInTheDocument();
  } else {
    expect(shared).not.toBeInTheDocument();
  }
});

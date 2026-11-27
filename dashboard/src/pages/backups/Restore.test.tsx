// SPDX-License-Identifier: Apache-2.0
import { configure, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import { seriousViolations } from '../../test/helpers';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

// The shared build worker can be heavily loaded; lazy screens then take longer than the 1 s default.
configure({ asyncUtilTimeout: 8000 });
const token = 'owner-demo';
const status = { health: 'ok', reason: null, last_success_at: '2026-11-14T12:00:00Z', last_verified_restore_at: null, next_run_at: null, badges: { box: { state: 'backed_up' } } };
const snapshots = [
  { id: 'a'.repeat(64), short_id: 'aaaaaaaa', unit: 'app:notes', app_id: 'notes', taken_at: '2026-11-20T03:00:00Z', reason: 'scheduled', paths: ['/data/notes'], verified_at: '2026-11-20T04:00:00Z' },
  { id: 'b'.repeat(64), short_id: 'bbbbbbbb', unit: 'system', app_id: null, taken_at: '2026-11-20T03:00:00Z', reason: 'scheduled', paths: [], verified_at: null },
];
const plan = { summary: 'Restore notes to 2026-11-20T03:00:00Z', steps: ['take a pre-restore snapshot of notes (the undo point)', 'stop notes'], downtime: 'the app is stopped during the restore', warnings: ['crash-consistent only'] };
function response(body: unknown, code = 200) { return new Response(JSON.stringify(body), { status: code, headers: { 'content-type': 'application/json' } }); }
function transport(extra?: (path: string, init?: RequestInit) => Response | undefined) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const custom = extra?.(path, init);
    if (custom) return custom;
    if (path === '/v1/backups/status') return response(status);
    if (path === '/v1/backups/destinations') return response([]);
    if (path === '/v1/backups/runs') return response([]);
    if (path === '/v1/backups/snapshots') return response(snapshots);
    if (path === '/v1/restores') return response([{ id: 'rst_1', action_id: 'act_9', state: 'succeeded', plan: { summary: 'Restore notes to an earlier day' }, pre_restore_snapshot_id: 'cccccccc1234', error: null }]);
    return response({ error: 'not_found', message: path }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
function mount() {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/backups']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
afterEach(() => vi.unstubAllGlobals());

it('lists real restore points and past restores with their undo snapshot', async () => {
  transport();
  mount();
  expect(await screen.findByRole('button', { name: /Restore notes from 2026-11-20/ })).toBeInTheDocument();
  expect(screen.getByText(/A whole-box restore runs when you set up a fresh box/)).toBeInTheDocument();
  expect(await screen.findByText('Restore notes to an earlier day')).toBeInTheDocument();
  expect(screen.getByText('cccccccc')).toBeInTheDocument();
});

it('says plainly that there are no restore points yet and that a destination is needed only if there is none', async () => {
  transport((path) => (path === '/v1/backups/snapshots' ? response([]) : undefined));
  mount();
  expect(await screen.findByText(/No restore points yet\. They appear after the first backup run; add a backup destination first if you have none\./)).toBeInTheDocument();
});

it('files an unapproved restore, shows the hub plan and the approval link, never approves', async () => {
  const fetch = transport((path, init) => {
    if (path === '/v1/restores' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      return response({ id: 'act_restore', type: 'backup.restore', state: 'awaiting_approval', idempotency_key: new Headers(init.headers).get('Idempotency-Key'), restore: { id: 'rst_2', plan }, _sent: body }, 202);
    }
  });
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: /Restore notes from/ }));
  const dialog = await screen.findByRole('alertdialog');
  await u.click(within(dialog).getByRole('radio', { name: /One folder only/ }));
  await u.click(within(dialog).getByRole('button', { name: 'File restore request' }));
  expect(await within(dialog).findByText('take a pre-restore snapshot of notes (the undo point)')).toBeInTheDocument();
  expect(within(dialog).getByText('crash-consistent only')).toBeInTheDocument();
  expect(within(dialog).getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_restore');
  const post = fetch.mock.calls.find(([, i]) => i?.method === 'POST')!;
  const sent = JSON.parse(String(post[1]!.body));
  expect(sent).toMatchObject({ snapshot_id: 'a'.repeat(64), scope: { app_id: 'notes', path: '/data/notes' }, mode: 'portable', target: 'in_place', approve: false });
  expect(fetch.mock.calls.some(([u2]) => String(u2).includes('/approve'))).toBe(false);
});

it('refuses a folder outside the restore point before sending anything', async () => {
  const fetch = transport();
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: /Restore notes from/ }));
  const dialog = await screen.findByRole('alertdialog');
  await u.click(within(dialog).getByRole('radio', { name: /One folder only/ }));
  const input = within(dialog).getByLabelText('Folder to put back');
  await u.clear(input);
  await u.type(input, '/etc/passwd');
  expect(within(dialog).getByRole('alert')).toHaveTextContent('inside this restore point');
  expect(within(dialog).getByRole('button', { name: 'File restore request' })).toBeDisabled();
  expect(fetch.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false);
});

it('adds an s3 destination as an approval request with write-only credentials', async () => {
  const fetch = transport((path, init) => {
    if (path === '/v1/backups/destinations' && init?.method === 'POST') {
      return response({ id: 'act_dest', type: 'backup.destination.add', state: 'awaiting_approval', idempotency_key: new Headers(init.headers).get('Idempotency-Key') }, 202);
    }
  });
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Add destination' }));
  const dialog = await screen.findByRole('alertdialog');
  const send = within(dialog).getByRole('button', { name: 'File request' });
  expect(send).toBeDisabled();
  await u.type(within(dialog).getByLabelText('Name'), 'Off-site');
  await u.type(within(dialog).getByLabelText(/Endpoint/), 'http://s3.example');
  expect(within(dialog).getByRole('alert')).toHaveTextContent('https://');
  await u.clear(within(dialog).getByLabelText(/Endpoint/));
  await u.type(within(dialog).getByLabelText(/Endpoint/), 'https://s3.example');
  await u.type(within(dialog).getByLabelText('Bucket'), 'omos');
  await u.type(within(dialog).getByLabelText('Access key'), 'AK');
  await u.type(within(dialog).getByLabelText('Secret key'), 'SK');
  expect(within(dialog).getByLabelText('Secret key')).toHaveAttribute('type', 'password');
  await u.click(send);
  expect(await screen.findByText(/Nothing was added yet/)).toBeInTheDocument();
  const post = fetch.mock.calls.find(([u2, i]) => String(u2).endsWith('/v1/backups/destinations') && i?.method === 'POST')!;
  expect(JSON.parse(String(post[1]!.body))).toMatchObject({ kind: 's3', label: 'Off-site', primary: false, approve: false,
    config: { endpoint: 'https://s3.example', bucket: 'omos' }, credentials: { access_key: 'AK', secret_key: 'SK' } });
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_dest');
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(document.body.textContent).not.toContain('SK');
});

it('has no axe violations in the wizard', async () => {
  transport();
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: /Restore notes from/ }));
  await screen.findByRole('alertdialog');
  expect(await seriousViolations(screen.getByRole('alertdialog'))).toEqual([]);
});

// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';
import { size } from './Content';

function mount(token = 'owner-demo') {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/backups']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const content = [{ app_id: 'jellyfin', name: 'Jellyfin', patterns: ['/cache/**'], enabled: false, size_bytes: 4_200_000_000, files: 1200, missing_volumes: [], enabled_at: null, enabled_size_bytes: null },
  { app_id: 'ollama', name: 'Ollama', patterns: [], enabled: true, size_bytes: null, files: null, missing_volumes: [], enabled_at: '2026-11-01T00:00:00Z', enabled_size_bytes: 8_000_000_000 }];
const checks = [{ id: 'v1', snapshot_id: 'abcdef123456', unit: 'app:photos', mode: 'scratch_restore', result: 'pass', finished_at: '2026-11-25T03:00:00Z', probes: {} },
  { id: 'v2', snapshot_id: null, unit: 'box', mode: 'check', result: 'fail', finished_at: null, probes: {} }];
function gateway(posts: { path: string; body: Record<string, unknown>; key: string | null }[], contentAnswer?: () => Response, listed: () => unknown = () => content) {
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    if (method === 'POST') {
      const body = JSON.parse(String(init!.body)) as Record<string, unknown>;
      posts.push({ path, body, key: new Headers(init!.headers).get('Idempotency-Key') });
      if (path === '/v1/backups/content' && contentAnswer) return contentAnswer();
      const type = path === '/v1/backups/verify' ? 'backup.verify' : 'backup.content.set';
      return json({ id: 'act_3', type, state: 'awaiting_approval', idempotency_key: new Headers(init!.headers).get('Idempotency-Key') }, 202);
    }
    if (path === '/v1/backups/content') return json(listed());
    if (path === '/v1/backups/verifications') return json(checks);
    if (path === '/v1/backups/status') return json({ health: 'ok', badges: { box: { state: 'backed_up' } } });
    if (path === '/v1/backups/destinations' || path === '/v1/backups/runs' || path === '/v1/backups/snapshots' || path === '/v1/restores') return json([]);
    return json({ error: 'not_found', message: path }, 404);
  }));
}
afterEach(() => vi.unstubAllGlobals());

it('writes sizes in plain units and says when one was not measured', () => {
  expect(size(4_200_000_000)).toBe('4.2 GB');
  expect(size(512)).toBe('512 bytes');
  // The same values as TestHumanBytesMatchesTheDashboard in cmd/onemind/cli/backup_content_test.go.
  expect(size(1_500_000_000)).toBe('1.5 GB');
  expect(size(1_250_000)).toBe('1.3 MB');
  expect(size(9_960_000_000)).toBe('10 GB');
  expect(size(15_400_000_000)).toBe('15 GB');
  expect(size(1_500_000_000_000)).toBe('1.5 TB');
  expect(size(null)).toBe('size not measured yet');
});

it('shows the check history in plain words', async () => {
  gateway([]);
  mount();
  const history = await screen.findByRole('list', { name: 'Check history' });
  expect(within(history).getByText('Passed')).toBeInTheDocument();
  expect(within(history).getByText('Failed')).toBeInTheDocument();
  expect(within(history).getByText(/Restore test of app:photos/)).toBeInTheDocument();
});

it('files a restore-test request without approving it', async () => {
  const posts: { path: string; body: Record<string, unknown>; key: string | null }[] = [];
  gateway(posts);
  mount();
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Ask for a check' }));
  expect(await screen.findByText(/Check requested; nothing runs until an owner approves it/)).toBeInTheDocument();
  expect(posts).toHaveLength(1);
  expect(posts[0]!.body).toMatchObject({ mode: 'scratch_restore', latest: true, approve: false });
  expect(posts[0]!.key).toMatch(/^[a-f0-9-]{36}$/);
});

it('shows the size before including content, then files that exact size as a request', async () => {
  const posts: { path: string; body: Record<string, unknown>; key: string | null }[] = [];
  gateway(posts);
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: "Include Jellyfin's content" }));
  expect(posts).toHaveLength(0);
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent(/adds about 4.2 GB to every backup/);
  await u.click(within(dialog).getByRole('button', { name: 'Send request' }));
  expect(await screen.findByText(/Back up Jellyfin's downloadable content: waiting for an owner/)).toBeInTheDocument();
  expect(posts).toHaveLength(1);
  expect(posts[0]!.body).toMatchObject({ app_id: 'jellyfin', enabled: true, seen_size_bytes: 4_200_000_000, approve: false });
});

it('files leaving content out, and cannot include content whose size is unknown', async () => {
  const posts: { path: string; body: Record<string, unknown>; key: string | null }[] = [];
  gateway(posts);
  mount();
  await userEvent.setup().click(await screen.findByRole('button', { name: "Leave out Ollama's content" }));
  expect(await screen.findByText(/Leave out Ollama's downloadable content/)).toBeInTheDocument();
  expect(posts[0]!.body).toMatchObject({ app_id: 'ollama', enabled: false });
  expect(posts[0]!.body.seen_size_bytes).toBeUndefined();
});

it('tells the owner when the content grew since the size was shown (409)', async () => {
  gateway([], () => json({ error: 'stale_precondition', message: 'jellyfin content is now bigger than the size shown', reason: 'size_changed' }, 409));
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: "Include Jellyfin's content" }));
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Send request' }));
  expect(await within(screen.getByRole('alertdialog')).findByRole('alert')).toHaveTextContent(/bigger than the size shown/);
});

it('reads the size again when it grew (409) and asks about the new size, not the old one', async () => {
  const posts: { path: string; body: Record<string, unknown>; key: string | null }[] = [];
  let bytes = 4_200_000_000;
  let refuse = true;
  gateway(posts, () => {
    if (refuse) { refuse = false; bytes = 9_000_000_000; return json({ error: 'stale_precondition', message: 'jellyfin content is now bigger than the size shown', reason: 'size_changed' }, 409); }
    return json({ id: 'act_4', type: 'backup.content.set', state: 'awaiting_approval', idempotency_key: posts.at(-1)!.key }, 202);
  }, () => [{ ...content[0], size_bytes: bytes }, content[1]]);
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: "Include Jellyfin's content" }));
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Send request' }));
  const dialog = screen.getByRole('alertdialog');
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(/now about 9.0 GB, not 4.2 GB/);
  expect(dialog).toHaveTextContent(/adds about 9.0 GB to every backup/);
  await u.click(within(dialog).getByRole('button', { name: 'Send request' }));
  expect(await screen.findByText(/Back up Jellyfin's downloadable content: waiting for an owner/)).toBeInTheDocument();
  expect(posts.map((p) => p.body.seen_size_bytes)).toEqual([4_200_000_000, 9_000_000_000]);
});

it('shows no include or leave-out buttons to an adult, because only an owner may change them', async () => {
  gateway([]);
  mount('adult-demo');
  expect(await screen.findByText('Only an owner can choose what goes into backups.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: "Include Jellyfin's content" })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: "Leave out Ollama's content" })).not.toBeInTheDocument();
});

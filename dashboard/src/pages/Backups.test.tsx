// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const token = 'owner-demo';
const status = { health: 'ok', agent: 'ok', reason: null, last_success_at: '2026-11-14T12:00:00Z', last_verified_restore_at: null, next_run_at: null, badges: { box: { state: 'backed_up' } } };
function mount() {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/backups']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
function response(body: unknown, code = 200) { return new Response(JSON.stringify(body), { status: code, headers: { 'content-type': 'application/json' } }); }
function transport(override?: (path: string, init?: RequestInit) => Response | Promise<Response> | undefined) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const custom = override?.(path, init);
    if (custom) return custom;
    if (path === '/v1/backups/status') return response(status);
    if (path === '/v1/backups/destinations') return response([{ id: 'target-1', label: 'Encrypted archive', kind: 's3', primary: true, append_only: true }]);
    if (path === '/v1/backups/runs') return response([{ id: 'run-1', state: 'succeeded', finished_at: '2026-11-14T12:00:00Z', error: null }]);
    return response({ error: 'not_found', message: path }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('reaches real backup status, targets and runs without inventing verified restore', async () => {
  const fetch = transport();
  mount();
  expect(await screen.findByRole('heading', { name: 'Backups', level: 1 })).toBeInTheDocument();
  expect(await screen.findByText('Encrypted archive')).toBeInTheDocument();
  expect(await screen.findByText('2026-11-14T12:00:00Z')).toBeInTheDocument();
  const summary = screen.getByRole('article', { name: 'Backup health' });
  expect(within(summary).getByText('backed_up')).toBeInTheDocument();
  expect(within(summary).getByText('Not verified')).toBeInTheDocument();
  expect(await screen.findByText('run-1')).toBeInTheDocument();
  expect(fetch.mock.calls.every(([, init]) => new Headers(init?.headers).get('authorization') === 'Bearer ' + token)).toBe(true);
  await userEvent.setup().click(screen.getAllByRole('link', { name: /Coming soon/ })[0]!);
  expect(screen.queryByRole('article', { name: 'Backups' })).not.toBeInTheDocument();
});

it('requires confirmation and files only an unapproved whole-box backup request', async () => {
  const fetch = transport((path, init) => {
    if (path === '/v1/backups/runs' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      return response({ id: 'backup-action', type: 'backup.run', state: 'awaiting_approval', params: { scope: 'box' }, idempotency_key: new Headers(init.headers).get('Idempotency-Key'), expires_at: body.expires_at }, 202);
    }
  });
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Request backup' }));
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent(/Nothing runs until the owner approves/);
  await u.click(within(dialog).getByRole('button', { name: 'Send request' }));
  expect(await screen.findByText(/backup-action: awaiting_approval/)).toBeInTheDocument();
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(posts).toHaveLength(1);
  expect(JSON.parse(String(posts[0]![1]?.body))).toEqual({ scope: 'box', approve: false, expires_at: expect.any(String) });
  expect(new Headers(posts[0]![1]?.headers).get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/);
  expect(fetch.mock.calls.some(([url]) => String(url).includes('/approve'))).toBe(false);
});

it.each(['missing', 'wrong_scope', 'wrong_identity', 'unknown_state'])('keeps exact retry identity for an ambiguous %s write reply', async (malformed) => {
  let sends = 0;
  const fetch = transport((path, init) => {
    if (path !== '/v1/backups/runs' || init?.method !== 'POST') return;
    const body = JSON.parse(String(init.body));
    const action = { id: 'retried-action', type: 'backup.run', state: 'awaiting_approval', params: { scope: 'box' }, idempotency_key: new Headers(init.headers).get('Idempotency-Key'), expires_at: body.expires_at };
    if (++sends === 1) return response(malformed === 'missing' ? {} : { ...action, ...(malformed === 'wrong_scope' ? { params: { scope: 'app:other' } } : malformed === 'wrong_identity' ? { idempotency_key: 'unrelated' } : { state: 'mystery' }) });
    return response(action, 202);
  });
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Request backup' }));
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Send request' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/may already have been filed/);
  expect(screen.queryByText(/No approval was sent/)).not.toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Retry same request' }));
  expect(await screen.findByText(/retried-action: awaiting_approval/)).toBeInTheDocument();
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(posts).toHaveLength(2);
  expect(posts[0]![1]?.body).toBe(posts[1]![1]?.body);
  expect(new Headers(posts[0]![1]?.headers).get('Idempotency-Key')).toBe(new Headers(posts[1]![1]?.headers).get('Idempotency-Key'));
});

it('lets the user start a new request only after the gateway conclusively rejects the old expiry', async () => {
  let sends = 0;
  const fetch = transport((path, init) => {
    if (path !== '/v1/backups/runs' || init?.method !== 'POST') return;
    if (++sends === 1) throw new TypeError('reply lost');
    if (sends === 2) return response({ error: 'expired', message: 'expires_at is already in the past' }, 409);
    const body = JSON.parse(String(init.body));
    return response({ id: 'fresh-action', type: 'backup.run', state: 'awaiting_approval', params: { scope: 'box' }, idempotency_key: new Headers(init.headers).get('Idempotency-Key'), expires_at: body.expires_at }, 202);
  });
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Request backup' }));
  await u.click(screen.getByRole('button', { name: 'Send request' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/may already have been filed/);
  expect(screen.queryByRole('button', { name: 'Start a new request' })).not.toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Retry same request' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/gateway confirmed.*expired/i);
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  await u.click(screen.getByRole('button', { name: 'Start a new request' }));
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  await u.click(screen.getByRole('button', { name: 'Send request' }));
  expect(await screen.findByText(/fresh-action: awaiting_approval/)).toBeInTheDocument();
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(posts[0]![1]?.body).toBe(posts[1]![1]?.body);
  expect(new Headers(posts[0]![1]?.headers).get('Idempotency-Key')).toBe(new Headers(posts[1]![1]?.headers).get('Idempotency-Key'));
  expect(new Headers(posts[2]![1]?.headers).get('Idempotency-Key')).not.toBe(new Headers(posts[0]![1]?.headers).get('Idempotency-Key'));
});

it('keeps the page usable when backup status is malformed', async () => {
  transport((path) => path === '/v1/backups/status' ? response({}) : undefined);
  mount();
  expect(await screen.findByText(/invalid backup status/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Backups', level: 1 })).toBeInTheDocument();
  expect(await screen.findByText('Encrypted archive')).toBeInTheDocument();
});

it('keeps an unconfirmed network write identity across in-tab navigation', async () => {
  let sends = 0;
  const fetch = transport((path, init) => {
    if (path !== '/v1/backups/runs' || init?.method !== 'POST') return;
    if (++sends === 1) throw new TypeError('reply lost');
    const body = JSON.parse(String(init.body));
    return response({ id: 'network-action', type: 'backup.run', state: 'awaiting_approval', params: { scope: 'box' }, idempotency_key: new Headers(init.headers).get('Idempotency-Key'), expires_at: body.expires_at }, 202);
  });
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Request backup' }));
  await u.click(screen.getByRole('button', { name: 'Send request' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/may already have been filed/);
  await u.click(screen.getByRole('button', { name: 'Close' }));
  await u.click(screen.getAllByRole('link', { name: /Coming soon/ })[0]!);
  await u.click(screen.getByRole('link', { name: 'Backups' }));
  await u.click(await screen.findByRole('button', { name: 'Request backup' }));
  await u.click(screen.getByRole('button', { name: /Send request|Retry same request/ }));
  expect(await screen.findByText(/network-action: awaiting_approval/)).toBeInTheDocument();
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(posts).toHaveLength(2);
  expect(posts[0]![1]?.body).toBe(posts[1]![1]?.body);
  expect(new Headers(posts[0]![1]?.headers).get('Idempotency-Key')).toBe(new Headers(posts[1]![1]?.headers).get('Idempotency-Key'));
});

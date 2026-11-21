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
const plan = { id: 'mig_1', app_id: 'blog', name: 'Blog', namespace: 'blog', state: 'planned', next: 'import', source: { server_host: 'old.example', context: 'ctx-a' }, bundle_sha256: 'sha256:abc',
  report: { blocking: [], counts: { workloads: 1 }, findings: [], volumes: [{ name: 'data' }] }, busy_action_id: null, old_replicas: null, last_error: null, copies: [] };
function mount() {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/migrate']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
function transport(over?: (path: string, init?: RequestInit) => Response | undefined) {
  const f = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url));
    const custom = over?.(u.pathname, init);
    if (custom) return custom;
    if (u.pathname === '/v1/instance') return json({ now: new Date().toISOString() });
    if (u.pathname === '/v1/migrate/plans' && init?.method !== 'POST') return json([plan]);
    if (u.pathname === '/v1/migrate/plans/mig_1') return json(plan);
    if (u.pathname === '/v1/migrate/plans/mig_1/helper') return json({ kind: 'Pod', note: 'PASSWORD_PLACEHOLDER' });
    if (u.pathname === '/v1/actions/act_1') return json({ id: 'act_1', state: 'awaiting_approval' });
    return json({ error: 'not_found', message: u.pathname }, 404);
  });
  vi.stubGlobal('fetch', f);
  return f;
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

async function fillPlan(u: ReturnType<typeof userEvent.setup>) {
  await u.click(await screen.findByLabelText(/Kubeconfig of the old cluster/, undefined, { timeout: 5000 }));
  await u.paste('apiVersion: v1');
  await u.type(screen.getByLabelText('Namespace'), 'blog');
}

it('shows the Market-id and already-installed 409s in plain words', async () => {
  let msg = "'ghost' is a Market app id; pick another with app_id";
  transport((path, init) => path === '/v1/migrate/plans' && init?.method === 'POST' ? json({ error: 'conflict', message: msg }, 409) : undefined);
  mount();
  const u = userEvent.setup();
  await fillPlan(u);
  await u.click(screen.getByRole('button', { name: 'Make a plan' }));
  expect(await screen.findByText(/That name is a Market app/)).toBeInTheDocument();
  msg = "an app 'blog' already exists on this box; pick another app_id";
  await u.click(screen.getByRole('button', { name: 'Make a plan' }));
  expect(await screen.findByText(/already installed on this box/)).toBeInTheDocument();
  expect(screen.getByRole('note')).toHaveTextContent(/only from an old cluster that is still running/);
});

it('plans, then files an import request bound to the bundle, and shows its progress', async () => {
  const f = transport((path, init) => {
    if (path === '/v1/migrate/plans' && init?.method === 'POST') return json(plan, 201);
    if (path === '/v1/migrate/plans/mig_1/import' && init?.method === 'POST') return json({ id: 'act_1', state: 'awaiting_approval' }, 202);
  });
  mount();
  const u = userEvent.setup();
  await fillPlan(u);
  await u.click(screen.getByRole('button', { name: 'Make a plan' }));
  expect(await screen.findByRole('article', { name: 'Blog (blog)' })).toBeInTheDocument();
  const plans = f.mock.calls.find(([url, init]) => String(url).endsWith('/v1/migrate/plans') && init?.method === 'POST')!;
  expect(JSON.parse(String(plans[1]?.body))).toMatchObject({ kubeconfig: 'apiVersion: v1', namespace: 'blog' });
  await u.click(screen.getByRole('button', { name: 'Request: Import the app' }));
  const dialog = await screen.findByRole('alertdialog');
  expect(within(dialog).getByText(/Nothing happens until the owner approves/)).toBeInTheDocument();
  await u.click(within(dialog).getByRole('button', { name: 'Send request' }));
  expect(await screen.findByText(/Request act_1: awaiting_approval/)).toBeInTheDocument();
  const call = f.mock.calls.find(([url]) => String(url).endsWith('/import'))!;
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({ bundle_sha256: 'sha256:abc' });
  expect(new Headers(call[1]?.headers).get('Idempotency-Key')).toBeTruthy();
  expect(window.sessionStorage.getItem('onemind.kubeconfig')).toBeNull();
});

it('copy needs the kubeconfig and previews the helper pod', async () => {
  const f = transport((path, init) => path === '/v1/migrate/plans/mig_1/copy' && init?.method === 'POST' ? json({ error: 'stale_precondition', message: 'cannot reach the cluster: refused' }, 409) : undefined);
  mount();
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: /Blog \(blog\)/ }, { timeout: 5000 }));
  await u.click(await screen.findByRole('button', { name: 'Preview helper pod for data' }));
  expect(await screen.findByLabelText('Helper pod preview')).toHaveTextContent('PASSWORD_PLACEHOLDER');
  await u.click(screen.getByRole('button', { name: 'Request: Copy the data' }));
  const dialog = await screen.findByRole('alertdialog');
  expect(within(dialog).getByRole('button', { name: 'Send request' })).toBeDisabled();
  await u.click(within(dialog).getByLabelText(/Kubeconfig of the old cluster/));
  await u.paste('apiVersion: v1');
  await u.click(within(dialog).getByRole('button', { name: 'Send request' }));
  expect(await within(dialog).findByText(/live old cluster/)).toBeInTheDocument();
  expect(f.mock.calls.some(([url]) => String(url).endsWith('/copy'))).toBe(true);
  const copy = f.mock.calls.find(([url]) => String(url).endsWith('/copy'));
  expect(JSON.parse(String(copy?.[1]?.body))).toMatchObject({ kubeconfig: 'apiVersion: v1', context: 'ctx-a' });
});

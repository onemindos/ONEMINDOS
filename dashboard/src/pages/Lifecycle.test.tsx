// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useNavigate, type NavigateFunction } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { ActionStatus } from '../shell/ActionJobs';

function setup(route = '/installed/uptime-kuma', failPlan = false, opts: { stopped?: boolean; progress?: boolean; enumKind?: 'number' | 'string'; delay?: boolean; malformed?: boolean } = {}) {
  let navigate: NavigateFunction;
  let release: (() => void) | undefined;
  function Navigation() { navigate = useNavigate(); return null; }
  const writes: Array<Record<string, unknown>> = [];
  const reads: string[] = [];
  const fetchFn = vi.fn(async (path: string, init?: RequestInit) => {
    path = new URL(path, window.location.origin).pathname + new URL(path, window.location.origin).search;
    reads.push(path);
    if (path.endsWith('/logs?tail=200')) return new Response('service ready\n', { headers: { 'Content-Type': 'text/plain' } });
    if (path.endsWith('/settings')) return Response.json({ fields: [{ name: 'theme', title: 'Theme', type: opts.enumKind ?? 'string', default: opts.enumKind === 'number' ? 10 : 'light', ...(opts.enumKind ? { enum: opts.enumKind === 'number' ? [10, 20] : ['light', 'dark'] } : {}) }], values: { theme: opts.enumKind === 'number' ? 10 : 'light' } });
    if (path === '/v1/actions') {
      const body = JSON.parse(init!.body as string);
      writes.push(body);
      if (opts.malformed && writes.length === 1) return Response.json({});
      return Response.json({ ...body, id: 'lifecycle-request', state: opts.progress ? 'dispatched' : 'awaiting_approval', ...(opts.progress ? { progress: { step: 'rolling workloads', pct: 42 } } : {}) });
    }
    if (failPlan) return Response.json({ error: 'permission_denied', message: 'Preview refused' }, { status: 403 });
    if (opts.delay) await new Promise<void>((resolve) => { release = resolve; });
    return Response.json({ plan: { summary: 'Gateway plan summary', objects: [], volumes: [{ effect: 'kept' }], warnings: ['Review this change'] }, plan_sha256: 'sha256:reviewed', app_id: path.includes('vaultwarden') ? 'vaultwarden' : 'uptime-kuma', type: path === '/v1/plans' ? JSON.parse(init!.body as string).type : 'app.install', policy_verdict: 'needs_approval', risk: 'write', reason: null });
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), {
    appPlan: http.appPlan.bind(http), previewAction: http.previewAction.bind(http),
    appSettings: http.appSettings.bind(http), appLogs: http.appLogs.bind(http), createAction: http.createAction.bind(http),
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  if (opts.stopped) {
    const apps = api.apps.bind(api);
    api.apps = async () => (await apps()).map((a) => a.id === 'uptime-kuma' ? { ...a, installed: false, status: 'stopped' } : a);
  }
  if (opts.progress && route.startsWith('/market')) {
    api.actions = async () => [{ id: 'market-progress', type: 'app.install', params: { app_id: 'vaultwarden' }, state: 'dispatched', progress: { step: 'gateway-reported step', pct: 42 }, idempotency_key: 'test-progress', expires_at: new Date(Date.now() + 600000).toISOString() }];
  }
  render(<MemoryRouter initialEntries={[route]}><Navigation /><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { writes, reads, user: userEvent.setup(), leave: () => navigate('/nodes'), release: () => release?.() };
}

describe('lifecycle through the HTTP client', () => {
  it('presents completed ledger status in a labelled card with an explained gateway result', () => {
    render(<ActionStatus label="App request progress" action={{ id: 'presentation-test', type: 'app.install', params: { app_id: 'uptime-kuma' }, state: 'succeeded', idempotency_key: 'presentation-test', expires_at: '2030-01-01T00:00:00Z', result: { outcome: 'succeeded', message: 'applied' } }} />);
    const panel = screen.getByRole('region', { name: 'App request progress' });
    expect(within(panel).getByRole('heading', { name: 'App request progress' })).toBeInTheDocument();
    expect(panel).toHaveClass('om-card');
    expect(within(panel).getByRole('status')).toHaveTextContent('Request status: succeeded');
    expect(within(panel).getByText('Gateway result: applied')).toBeInTheDocument();
    expect(within(panel).queryByText('Healthy')).not.toBeInTheDocument();
  });
  it('keeps the compact jobs island and expands to actual ledger state', async () => {
    const { user } = setup();
    const tray = await screen.findByRole('complementary', { name: 'Jobs in progress' });
    const toggle = within(tray).getByRole('button', { name: '1 job · Ollama: Awaiting approval' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveClass('om-store-tray-pill');
    expect(within(tray).queryByRole('region', { name: 'Request progress' })).not.toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const progress = within(tray).getByRole('region', { name: 'Request progress' });
    expect(progress).toHaveTextContent('awaiting approval');
    expect(progress.parentElement?.tagName).toBe('DIV');
  });
  it('does not announce an incomplete write response as success and reuses the retry identity', async () => {
    const { user, writes } = setup('/installed/uptime-kuma', false, { malformed: true });
    const send = async () => {
      await user.click(await screen.findByRole('button', { name: 'Restart' }));
      await user.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    };
    await send();
    expect(await screen.findByText(/may have been recorded/)).toBeInTheDocument();
    expect(screen.queryByText('Request sent')).not.toBeInTheDocument();
    await send();
    await screen.findByText('Request sent');
    expect(writes).toHaveLength(2);
    expect(writes[1]).toEqual(writes[0]);
  });
  it('shows unscaled executor progress on the app detail route without invented phases', async () => {
    setup('/market/vaultwarden', false, { progress: true });
    const panel = await screen.findByRole('region', { name: 'App request progress' });
    expect(within(panel).getByRole('progressbar')).toHaveAttribute('value', '42');
    expect(panel).toHaveTextContent('gateway-reported step');
    expect(screen.queryByText('Pulling image')).not.toBeInTheDocument();
  });
  it.each(['number', 'string'] as const)('preserves %s enum values', async (enumKind) => {
    const { user, writes } = setup('/installed/uptime-kuma', false, { enumKind });
    await user.selectOptions(await screen.findByLabelText('Theme'), enumKind === 'number' ? '20' : 'dark');
    await user.click(screen.getByRole('button', { name: 'Review settings' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes[0]).toMatchObject({ params: { settings: { theme: enumKind === 'number' ? 20 : 'dark' } } }));
  });

  it('invalidates a delayed preview after navigation', async () => {
    const { user, reads, writes, leave, release } = setup('/market/vaultwarden', false, { delay: true });
    await user.click(await screen.findByRole('button', { name: /Request install/ }));
    await waitFor(() => expect(reads).toContain('/v1/apps/vaultwarden/plan'));
    act(leave);
    await act(async () => release());
    expect(screen.queryByRole('dialog', { name: 'Review app request' })).not.toBeInTheDocument();
    expect(writes).toHaveLength(0);
  });

  it('cancels an open review when navigating to another route', async () => {
    const { user, writes, leave } = setup('/market/vaultwarden');
    await user.click(await screen.findByRole('button', { name: /Request install/ }));
    await screen.findByRole('dialog', { name: 'Review app request' });
    act(leave);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Review app request' })).not.toBeInTheDocument());
    expect(writes).toHaveLength(0);
  });
  it.each([['Stop', 'app.stop'], ['Review update', 'app.update'], ['Remove…', 'app.remove']])('files %s only after review', async (label, type) => {
    const { user, writes } = setup();
    await user.click(await screen.findByRole('button', { name: label }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes[0]).toMatchObject({ type, params: { app_id: 'uptime-kuma' } }));
  });

  it('starts a stopped app even though the catalog installed flag is false', async () => {
    const { user, writes } = setup('/installed/uptime-kuma', false, { stopped: true });
    await user.click(await screen.findByRole('button', { name: 'Start' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes[0]).toMatchObject({ type: 'app.start' }));
  });

  it('loads settings and logs and sends changed settings through plan review', async () => {
    const { user, writes, reads } = setup();
    expect(await screen.findByText('service ready')).toBeInTheDocument();
    const field = await screen.findByLabelText('Theme');
    await user.clear(field);
    await user.type(field, 'dark');
    await user.click(screen.getByRole('button', { name: 'Review settings' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes[0]).toMatchObject({ type: 'app.configure', params: { app_id: 'uptime-kuma', settings: { theme: 'dark' } } }));
    expect(reads).toContain('/v1/apps/uptime-kuma/settings');
  });

  it('shows the executor step and percentage in the global jobs tray', async () => {
    const { user } = setup('/installed/uptime-kuma', false, { progress: true });
    await user.click(await screen.findByRole('button', { name: 'Restart' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Review app request' })).getByRole('button', { name: 'Send request' }));
    const tray = await screen.findByRole('complementary', { name: 'Jobs in progress' });
    await user.click(within(tray).getByRole('button', { expanded: false }));
    expect(within(tray).getByRole('progressbar', { name: 'app.restart progress' })).toHaveAttribute('value', '42');
  });
  it('previews Restart, binds the request to that plan, and never approves it', async () => {
    const { user, writes, reads } = setup();
    await user.click(await screen.findByRole('button', { name: /^Restart$/ }));
    const review = await screen.findByRole('dialog', { name: 'Review app request' });
    expect(review).toHaveTextContent('Gateway plan summary');
    expect(writes).toHaveLength(0);
    await user.click(within(review).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ type: 'app.restart', params: { app_id: 'uptime-kuma' }, plan_sha256: 'sha256:reviewed' });
    expect(reads.some((p) => p.includes('/approve'))).toBe(false);
    expect(screen.queryByText(/not on this hub yet/)).not.toBeInTheDocument();
  });

  it('gets the install plan from the app route and cancellation files nothing', async () => {
    const { user, writes, reads } = setup('/market/vaultwarden');
    await user.click(await screen.findByRole('button', { name: /Request install/ }));
    const review = await screen.findByRole('dialog', { name: 'Review app request' });
    expect(reads).toContain('/v1/apps/vaultwarden/plan');
    await user.click(within(review).getByRole('button', { name: 'Cancel' }));
    expect(writes).toHaveLength(0);
  });

  it('never sends an action when plan loading fails', async () => {
    const { user, writes } = setup('/market/vaultwarden', true);
    await user.click(await screen.findByRole('button', { name: /Request install/ }));
    expect(await screen.findByText(/Your account is not allowed/)).toBeInTheDocument();
    expect(writes).toHaveLength(0);
  });
});

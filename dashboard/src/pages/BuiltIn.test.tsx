// SPDX-License-Identifier: Apache-2.0
// #617: the Market's Built in tab and Settings → Apps render GET /v1/system-apps (a response captured from
// the real gateway, test/fixtures/system-apps.json). Switching off says what else stops, then files an
// app.disable approval; apps that can never be switched off show no switch.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { toRoute } from '../shell/routes';
import { appDeepLink, appWebPath, deepLinkToPath } from '../lib/appLinks';

interface Fixture { system_apps: Array<Record<string, unknown> & { id: string; name: string; can_disable: boolean }>; notebook_dependencies: unknown }
const FIXTURE = Object.values(import.meta.glob('../test/fixtures/system-apps.json', { eager: true, import: 'default' }))[0] as Fixture;
// The committed OpenAPI spec, as text (Vite inlines it at test time).
const SPEC = Object.values(import.meta.glob('../../../sdk/openapi/onemind-v1.json', { query: '?raw', import: 'default', eager: true }) as Record<string, string>)[0] ?? '{}';
const NEVER_OFF = ['Approvals', 'Backups', 'Files', 'Market', 'Notifications', 'Settings', 'Updates'];

function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }

function mount(route: string, token: keyof typeof DEMO_TOKENS = 'owner-demo', notebookOn = true) {
  const calls: Array<{ method: string; path: string; body: Record<string, unknown> | undefined }> = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : undefined;
    calls.push({ method, path, body });
    if (path === '/v1/system-apps') return response(FIXTURE.system_apps.map((row) =>
      row.id === 'notebook' ? { ...row, enabled: notebookOn } : row));
    if (path === '/v1/settings/photos' && method === 'GET') return response({
      enabled: false, owner_switch_on: false, operator_off: false,
      can_change: token === 'owner-demo', pending_action_id: null,
    });
    if (path === '/v1/apps/notebook/dependencies') return response(FIXTURE.notebook_dependencies);
    if (path === '/v1/instance') return response({ name: 'test-box', version: '0.0.0' });
    if (path === '/v1/actions' && method === 'POST') return response({ id: 'act-617', state: 'awaiting_approval', requested_by: 'owner', created_at: '2026-11-22T00:00:00Z', ...body }, 201);
    return response({ error: 'not_found', message: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={[route]}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

/** The app's card: its level-3 heading inside an om-card (the settings frame has headings of its own). */
const card = (name: string) => screen.getAllByRole('heading', { name, level: 3 }).map((h) => h.closest('section.om-card')).find(Boolean) as HTMLElement;

describe('Built in (#617)', () => {
  it('the fixture is the real gateway answer: the signed list (os/rootfs/.../system-apps.json) with every SystemAppRow field', () => {
    expect(FIXTURE.system_apps.map((r) => r.name).sort()).toEqual([...NEVER_OFF, 'Notebook', 'Photos'].sort());
    const fields = Object.keys((JSON.parse(SPEC) as { components: { schemas: Record<string, { properties: Record<string, unknown> }> } }).components.schemas.SystemAppRow!.properties).sort();
    for (const r of FIXTURE.system_apps) expect(Object.keys(r).sort()).toEqual(fields);
  });

  it('the Market tab lists every built-in app with version, update channel and licence; never-off apps show no switch', async () => {
    const calls = mount('/built-in');
    expect(await screen.findByRole('heading', { name: 'Notebook' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Built in' })).toHaveAttribute('aria-current', 'page');
    const notebook = within(card('Notebook')).getByLabelText('Notebook licence card');
    expect(within(notebook).getByText('1.0.0')).toBeInTheDocument();
    expect(within(notebook).getByText('Stable')).toBeInTheDocument();
    expect(within(notebook).getByText('MIT')).toBeInTheDocument();
    expect(within(notebook).getByText('onemind://app/notebook')).toBeInTheDocument();
    expect(within(card('Photos')).getByText('2026-11-11')).toBeInTheDocument();
    for (const name of NEVER_OFF) {
      expect(within(card(name)).queryByRole('switch')).toBeNull();
      expect(within(card(name)).getByText('Always on')).toBeInTheDocument();
    }
    expect(await screen.findByRole('switch', { name: 'Photos: off' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getAllByRole('switch')).toHaveLength(2);
    expect(screen.getByRole('switch', { name: 'Notebook: on' })).toHaveAttribute('aria-checked', 'true');
    expect(calls.some((c) => c.method === 'GET' && c.path === '/v1/system-apps')).toBe(true);
  });

  it('switching off shows what else stops before acting, then files an app.disable approval', async () => {
    const calls = mount('/built-in');
    const u = userEvent.setup();
    await u.click(await screen.findByRole('switch', { name: 'Notebook: on' }));
    const dialog = await screen.findByRole('dialog', { name: 'Switch off Notebook?' });
    expect(within(dialog).getByText(/Journal stops working: it needs Notebook/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);

    await u.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(calls.some((c) => c.method === 'POST')).toBe(false);

    await u.click(screen.getByRole('switch', { name: 'Notebook: on' }));
    await u.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Ask to switch off' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/v1/actions')).toBeDefined());
    const post = calls.find((c) => c.method === 'POST' && c.path === '/v1/actions')!;
    expect(post.body).toMatchObject({ type: 'app.disable', params: { app_id: 'notebook' } });
    expect(post.body).not.toHaveProperty('approve');
    expect(await screen.findByText(/waits in Approvals/)).toBeInTheDocument();
  });

  it('switching a switched-off app back on files an app.enable approval', async () => {
    const calls = mount('/built-in', 'owner-demo', false);
    await userEvent.setup().click(await screen.findByRole('switch', { name: 'Notebook: off' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/v1/actions')?.body)
      .toMatchObject({ type: 'app.enable', params: { app_id: 'notebook' } }));
  });

  it('Settings → Apps shows the same list from the same route', async () => {
    const calls = mount('/settings/apps');
    expect(await screen.findByRole('heading', { name: 'Built-in apps' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Photos' })).toBeInTheDocument();
    for (const name of NEVER_OFF) expect(within(card(name)).queryByRole('switch')).toBeNull();
    expect(screen.getByRole('switch', { name: 'Notebook: on' })).toBeInTheDocument();
    expect(calls.some((c) => c.path === '/v1/system-apps')).toBe(true);
  });

  it('an account that cannot request sees the list but no switch', async () => {
    mount('/built-in', 'guest-demo');
    expect(await screen.findByRole('heading', { name: 'Notebook' })).toBeInTheDocument();
    expect(screen.queryAllByRole('switch')).toHaveLength(0);
  });
});

describe('onemind://app deep links (#617)', () => {
  it('builds the link and its matching web path', () => {
    expect(appDeepLink('notebook', 'logs')).toBe('onemind://app/notebook/logs');
    expect(appDeepLink('photos')).toBe('onemind://app/photos');
    expect(appWebPath('notebook', 'logs')).toBe('/apps/notebook/logs');
    expect(deepLinkToPath('onemind://app/notebook/logs?x=1')).toBe('/apps/notebook/logs');
    expect(toRoute('onemind://app/settings/apps')).toBe('/apps/settings/apps');
  });

  it('refuses links that could leave the app or the dashboard', () => {
    for (const bad of ['onemind://app/../x', 'onemind://app/Bad_Id', 'onemind://app/x/..', 'onemind://app/x/%2e%2e', 'onemind://app/x/a:b', 'onemind://evil/x', 'onemind://app/']) {
      expect(toRoute(bad)).toBeUndefined();
    }
    expect(appDeepLink('x', '../../etc')).toBeUndefined();
  });

  it('the web path of a built-in app the dashboard draws opens its own screen', async () => {
    mount('/apps/settings/apps');
    expect(await screen.findByRole('heading', { name: 'Built-in apps' })).toBeInTheDocument();
  });
});

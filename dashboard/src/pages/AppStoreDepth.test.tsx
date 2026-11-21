// SPDX-License-Identifier: Apache-2.0
// #143: the app store depth flows end to end through HttpApi against the #57 routes (§12.22):
// typed settings, dependencies and alternatives, host ports, a pinned community source, Compose import.
// Every change is a request that waits in Approvals; reads and the Compose conversion write nothing.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const COMMIT = 'a'.repeat(40);
const FILES = { 'onemind.app.yaml': 'kind: App\n', 'manifests/kustomization.yaml': 'resources: []\n' };

function setup(route: string, opts: { refuse?: boolean; conflict?: boolean; role?: 'owner' | 'adult'; installed?: string[]; actionReplies?: Array<(body: Record<string, unknown>) => Response> } = {}) {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  const reads: string[] = [];
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, window.location.origin);
    const path = u.pathname;
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    if (init?.method === 'POST' && path !== '/v1/plans') writes.push({ path, body });
    else reads.push(path);
    const app = path.split('/')[3] ?? '';
    if (path.endsWith('/settings')) return Response.json({ app_id: app, fields: [{ name: 'retention_days', env: 'RETENTION_DAYS', title: 'Retention days', type: 'integer', default: 30, minimum: 1, maximum: 365, restart: true }], values: { retention_days: 30 }, updated_at: null, action_id: null });
    if (path.endsWith('/dependencies')) return Response.json(app === 'zigbee2mqtt'
      ? { app_id: app, requires: [{ id: 'mosquitto', alternatives: ['emqx'], reason: 'MQTT broker', port: 1883, satisfied_by: null, choices: [{ id: 'mosquitto', name: 'Mosquitto', in_catalog: true, installed: false }, { id: 'emqx', name: null, in_catalog: false, installed: false }] }], dependents: [] }
      : { app_id: app, requires: [], dependents: [{ id: 'zigbee2mqtt', name: 'Zigbee2MQTT' }] });
    if (path.endsWith('/host-ports')) return Response.json({ app_id: app, node_id: 'hub', declared: [{ port: 1900, protocol: 'UDP', description: 'DLNA discovery' }], conflicts: opts.conflict ? [{ port: 1900, protocol: 'UDP', with: 'onemind:ssdp' }] : [] });
    if (path === '/v1/sources') return Response.json([{ id: 'src_01J0000000000000000000000A', name: 'friends', url: 'https://git.example.org/apps', commit: 'b'.repeat(40), state: 'ready', added_by: 'owner', added_at: null, updated_at: null, action_id: null, apps: [{ id: 'whoami', version: '1.0', scan: { result: 'pass', scanned_at: null, checks: [] } }], errors: [] }]);
    if (path === '/v1/deploy/compose') return Response.json(opts.refuse
      ? { ok: false, app_id: body.app_id, files: {}, refusals: [{ service: 'web', rule: 'F-06', field: 'services.web.privileged', message: 'a privileged container is root on the host' }], warnings: [] }
      : { ok: true, app_id: body.app_id, files: FILES, refusals: [], warnings: ['services.web.ports: 8080 becomes a Service port'] });
    if (path === '/v1/actions') return opts.actionReplies?.shift()?.(body) ?? Response.json({ ...body, id: 'act-1', state: 'awaiting_approval' });
    const plan = path === '/v1/plans' ? body : { type: 'app.install', params: { app_id: app } };
    return Response.json({ plan: { summary: `Plan for ${plan.params.app_id}` }, plan_sha256: 'sha256:reviewed', app_id: plan.params.app_id, type: plan.type, policy_verdict: 'needs_approval', risk: 'write', reason: null });
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), {
    appPlan: http.appPlan.bind(http), previewAction: http.previewAction.bind(http), appSettings: http.appSettings.bind(http),
    appLogs: async () => '', createAction: http.createAction.bind(http), appDependencies: http.appDependencies.bind(http),
    appHostPorts: http.appHostPorts.bind(http), sources: http.sources.bind(http), requestSourceAdd: http.requestSourceAdd.bind(http),
    convertCompose: http.convertCompose.bind(http),
  });
  if (opts.installed) {
    const apps = api.apps.bind(api);
    api.apps = async () => (await apps()).map((a) => (opts.installed!.includes(a.id) ? { ...a, installed: true, status: 'installed' } : a));
  }
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={[route]}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-user', kind: 'person', role: opts.role ?? 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { writes, reads, user: userEvent.setup() };
}

const send = async (user: ReturnType<typeof userEvent.setup>, dialog = 'Review app request') =>
  user.click(within(await screen.findByRole('dialog', { name: dialog })).getByRole('button', { name: 'Send request' }));

describe('app store depth (#143) against the #57 routes', () => {
  it('builds the settings form from the typed schema and refuses an out-of-range value before any request', async () => {
    const { user, writes } = setup('/installed/uptime-kuma');
    const field = await screen.findByLabelText('Retention days');
    expect(field).toHaveAttribute('min', '1');
    expect(field).toHaveAttribute('max', '365');
    await user.clear(field);
    await user.type(field, '900');
    await user.click(screen.getByRole('button', { name: 'Review settings' }));
    expect(await screen.findByText(/Retention days:/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Review app request' })).not.toBeInTheDocument();
    await user.clear(field);
    await user.type(field, '90');
    expect(screen.getByText(/Changing this restarts the app/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review settings' }));
    await send(user);
    await waitFor(() => expect(writes).toContainEqual(expect.objectContaining({ path: '/v1/actions', body: expect.objectContaining({ type: 'app.configure', params: { app_id: 'uptime-kuma', settings: { retention_days: 90 } }, plan_sha256: 'sha256:reviewed' }) })));
  });

  it('shows a missing dependency with its alternatives and requests the provider through approval', async () => {
    const { user, writes } = setup('/market/zigbee2mqtt');
    const deps = await screen.findByRole('region', { name: 'Dependencies' });
    expect(await within(deps).findByText(/Needs Mosquitto or emqx/)).toBeInTheDocument();
    expect(within(deps).getByText(/Missing: install one of these first/)).toBeInTheDocument();
    expect(within(deps).getByText(/emqx \(not in the catalog\)/)).toBeInTheDocument();
    expect(within(deps).getByRole('link', { name: 'Mosquitto' })).toHaveAttribute('href', '/market/mosquitto');
    await user.click(within(deps).getByRole('button', { name: 'Request install of Mosquitto' }));
    await send(user);
    await waitFor(() => expect(writes).toContainEqual(expect.objectContaining({ body: expect.objectContaining({ type: 'app.install', params: { app_id: 'mosquitto' } }) })));
  });

  it('names the apps that depend on this one, and lists host ports with their conflicts', async () => {
    setup('/installed/mosquitto', { conflict: true });
    expect(await screen.findByText(/depend on this one: Zigbee2MQTT/)).toBeInTheDocument();
    const ports = screen.getByRole('region', { name: 'Host ports' });
    expect(await within(ports).findByRole('cell', { name: 'DLNA discovery' })).toBeInTheDocument();
    expect(within(ports).getByRole('alert')).toHaveTextContent('1900/UDP is held by OneMind (ssdp)');
  });

  it('lists pinned sources and files source.add as a request that waits for the owner', async () => {
    const { user, writes } = setup('/sources');
    expect(await screen.findByText('friends')).toBeInTheDocument();
    expect(screen.getByText(/scan: pass/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Name'), 'more-apps');
    await user.type(screen.getByLabelText('Git URL'), 'https://git.example.org/more');
    await user.type(screen.getByLabelText('Commit'), COMMIT.toUpperCase());
    await user.click(screen.getByRole('button', { name: 'Review source' }));
    expect(writes).toHaveLength(0);
    await send(user, 'Review source request');
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({ path: '/v1/actions', body: { type: 'source.add', params: { name: 'more-apps', url: 'https://git.example.org/more', commit: COMMIT } } });
    expect(writes[0]!.body).not.toHaveProperty('approve');
    expect(await screen.findByText('Request sent')).toBeInTheDocument();
  });

  it('converts a Compose file without installing anything, and shows sandbox refusals', async () => {
    const { user, writes } = setup('/compose');
    await user.type(await screen.findByLabelText('App id'), 'whoami');
    await user.type(screen.getByLabelText('Compose file'), 'services: {{}');
    await user.click(screen.getByRole('button', { name: 'Convert' }));
    const result = await screen.findByRole('region', { name: 'Conversion result' });
    expect(within(result).getByRole('heading', { name: 'Converted whoami' })).toBeInTheDocument();
    expect(within(result).getByText('onemind.app.yaml')).toBeInTheDocument();
    expect(within(result).getByText(/becomes a Service port/)).toBeInTheDocument();
    expect(writes.map((w) => w.path)).toEqual(['/v1/deploy/compose']);
    expect(writes[0]!.body).toEqual({ app_id: 'whoami', compose: 'services: {}' });
  });

  it('shows a refused Compose conversion with its rule id', async () => {
    const { user } = setup('/compose', { refuse: true });
    await user.type(await screen.findByLabelText('App id'), 'bad');
    await user.type(screen.getByLabelText('Compose file'), 'x');
    await user.click(screen.getByRole('button', { name: 'Convert' }));
    expect(await screen.findByRole('heading', { name: 'bad cannot be imported' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('F-06 (web) services.web.privileged');
  });

  it('says an installed app with a removed dependency may not work, instead of the install gate', async () => {
    setup('/installed/zigbee2mqtt', { installed: ['zigbee2mqtt'] });
    const deps = await screen.findByRole('region', { name: 'Dependencies' });
    expect(await within(deps).findByText(/no app that provides this is installed, so this app may not work/)).toBeInTheDocument();
    expect(within(deps).queryByText(/install request is refused/)).not.toBeInTheDocument();
  });

  it('keeps the idempotency key when source.add times out (408), so the retry cannot file a second request', async () => {
    const { user, writes } = setup('/sources', { actionReplies: [() => new Response(null, { status: 408 })] });
    await user.type(await screen.findByLabelText('Name'), 'more-apps');
    await user.type(screen.getByLabelText('Git URL'), 'https://git.example.org/more');
    await user.type(screen.getByLabelText('Commit'), COMMIT);
    await user.click(screen.getByRole('button', { name: 'Review source' }));
    await send(user, 'Review source request');
    expect(await screen.findByText('Could not request the source')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review source' }));
    await send(user, 'Review source request');
    expect(await screen.findByText('Request sent')).toBeInTheDocument();
    expect(writes).toHaveLength(2);
    expect(writes[1]!.body.idempotency_key).toBe(writes[0]!.body.idempotency_key);
    expect(writes[1]!.body.expires_at).toBe(writes[0]!.body.expires_at);
  });

  it('treats a source.add reply that is not the request it sent as outcome unknown', async () => {
    const fetchFor = (reply: (b: Record<string, unknown>) => Record<string, unknown>) => new HttpApi({ token: 'test-only', fetchFn: vi.fn(async (_u: string, init?: RequestInit) => Response.json(reply(JSON.parse(init!.body as string)))) });
    const params = { name: 'more-apps', url: 'https://git.example.org/more', commit: COMMIT };
    const key = { idempotency_key: 'k-1', expires_at: '2026-11-19T00:00:00.000Z' };
    const ok = (b: Record<string, unknown>) => ({ ...b, id: 'act-1', state: 'awaiting_approval' });
    await expect(fetchFor(ok).requestSourceAdd(params, key)).resolves.toMatchObject({ id: 'act-1' });
    for (const bad of [
      (b: Record<string, unknown>) => ({ ...ok(b), params: { ...params, commit: 'c'.repeat(40) } }),
      (b: Record<string, unknown>) => ({ ...ok(b), expires_at: '2026-11-20T00:00:00.000Z' }),
      (b: Record<string, unknown>) => ({ ...ok(b), state: 'bogus' }),
      (b: Record<string, unknown>) => ({ ...ok(b), idempotency_key: 'k-2' }),
    ]) await expect(fetchFor(bad).requestSourceAdd(params, key)).rejects.toMatchObject({ code: 'outcome_unknown' });
  });

  it('tells a non-owner up front that sources and Compose import are owner-only, and sends nothing', async () => {
    const { user, writes } = setup('/sources', { role: 'adult' });
    expect(await screen.findByText(/Only an owner can add a source/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review source' })).toBeDisabled();
    await user.click(screen.getByRole('link', { name: 'Import Compose' }));
    expect(await screen.findByText(/Only an owner can import a Compose file/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Convert' })).toBeDisabled();
    expect(writes).toHaveLength(0);
  });
});

describe('app store depth in demo mode (MockApi)', () => {
  it('serves dependencies and host ports from the demo catalog', async () => {
    const api = new MockApi('owner-demo');
    const z = await api.appDependencies('zigbee2mqtt');
    expect(z.requires[0]).toMatchObject({ id: 'mosquitto', satisfied_by: null, choices: [{ id: 'mosquitto', name: 'Mosquitto', in_catalog: true, installed: false }, { id: 'emqx', in_catalog: false }] });
    expect((await api.appDependencies('uptime-kuma')).requires).toEqual([]);
    expect((await api.appHostPorts('mosquitto')).declared).toEqual([{ port: 1883, protocol: 'TCP', description: 'MQTT clients' }]);
    await expect(api.appHostPorts('nope')).rejects.toMatchObject({ status: 404 });
  });

  it('shows the depth sections on a demo app page without a cannot-be-read alert', async () => {
    window.sessionStorage.setItem('onemind.token', 'owner-demo');
    render(<MemoryRouter initialEntries={['/market/mosquitto']}><SessionProvider deps={{ mock: true, makeApi: (t) => new MockApi(t) }}><App mock /></SessionProvider></MemoryRouter>);
    const ports = await screen.findByRole('region', { name: 'Host ports' });
    expect(await within(ports).findByRole('cell', { name: 'MQTT clients' })).toBeInTheDocument();
    expect(await within(screen.getByRole('region', { name: 'Dependencies' })).findByText('This app needs no other app.')).toBeInTheDocument();
    expect(screen.queryByText(/cannot be read by this gateway client/)).not.toBeInTheDocument();
  });
});

// SPDX-License-Identifier: Apache-2.0
// The Photos switch in Settings → Apps (refs #1232, #234): GET /v1/settings/photos through @onemind/sdk;
// the switch only files an app.enable / app.disable request that waits in Approvals.
import type { Action, components } from '@onemind/sdk';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, expectTypeOf, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { readPhotosSwitch, requestPhotosSwitch } from './PhotosSwitch';

function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }

function mount(state: Record<string, unknown>, token: keyof typeof DEMO_TOKENS = 'owner-demo') {
  const calls: Array<{ method: string; path: string; body: Record<string, unknown> | undefined }> = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : undefined;
    calls.push({ method, path, body });
    if (path === '/v1/settings/photos' && method === 'GET') return response(state);
    if (path === '/v1/settings/photos' && method === 'PUT') return response({ id: 'act-photos', type: body?.enabled ? 'app.enable' : 'app.disable', state: 'awaiting_approval' }, 202);
    if (path === '/v1/system-apps') return response([
      { id: 'photos', name: 'Photos', kind: 'native', disable: 'allowed', can_disable: true, enabled: true,
        update: 'os', update_channel: 'os', version: null, license: 'Apache-2.0' },
    ]);
    if (path === '/v1/instance') return response({ name: 'test-box', version: '0.0.0' });
    return response({ error: 'not_found', message: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/apps']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

const ON = { enabled: true, owner_switch_on: true, operator_off: false, can_change: true, pending_action_id: null };

it('uses the generated Photos settings and Action contracts', () => {
  expectTypeOf(readPhotosSwitch).returns.toEqualTypeOf<Promise<components['schemas']['PhotosSwitch']>>();
  expectTypeOf(requestPhotosSwitch).returns.toEqualTypeOf<Promise<Action>>();
});

it('shows Photos as on by default and asks to switch it off with a PUT; nothing is changed by the click itself', async () => {
  const calls = mount(ON);
  const sw = await screen.findByRole('switch', { name: 'Photos: on' });
  expect(sw).toHaveAttribute('aria-checked', 'true');
  expect(screen.getAllByRole('heading', { name: 'Photos' })).toHaveLength(1);
  await userEvent.setup().click(sw);
  await vi.waitFor(() => expect(calls.filter((c) => c.method === 'PUT')).toEqual([{ method: 'PUT', path: '/v1/settings/photos', body: { enabled: false } }]));
  // the click takes the person to Approvals, where the request waits
  expect(await screen.findByRole('heading', { name: /approvals/i })).toBeInTheDocument();
});

it('asks to switch it back on from the off state', async () => {
  const calls = mount({ ...ON, enabled: false, owner_switch_on: false });
  await userEvent.setup().click(await screen.findByRole('switch', { name: 'Photos: off' }));
  await vi.waitFor(() => expect(calls.filter((c) => c.method === 'PUT')[0]?.body).toEqual({ enabled: true }));
});

it('shows a waiting request and disables the switch', async () => {
  mount({ ...ON, pending_action_id: 'act-9' });
  const sw = await screen.findByRole('switch', { name: 'Photos: on' });
  expect(sw).toBeDisabled();
  expect(screen.getByText('Waiting for approval')).toBeInTheDocument();
});

it('shows no switch when an operator turned Photos off in the box configuration', async () => {
  mount({ enabled: false, owner_switch_on: true, operator_off: true, can_change: false, pending_action_id: null });
  expect(await screen.findByLabelText('Photos licence card')).toBeInTheDocument();
  expect(await screen.findByText(/Switched off in the box's configuration/)).toBeInTheDocument();
  expect(screen.getByText('Off')).toBeInTheDocument();
  expect(screen.queryByText('On')).toBeNull();
  expect(screen.queryByRole('switch', { name: /^Photos:/ })).toBeNull();
});

it('offers no switch to an adult, who is always refused by the API', async () => {
  const calls = mount(ON, 'adult-demo');
  expect(await screen.findByLabelText('Photos licence card')).toBeInTheDocument();
  expect(await screen.findByText('Only an owner can change this.')).toBeInTheDocument();
  expect(screen.queryByRole('switch', { name: /^Photos:/ })).toBeNull();
  expect(calls.filter((c) => c.method === 'PUT')).toEqual([]);
});

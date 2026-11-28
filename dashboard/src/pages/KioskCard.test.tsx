// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

function response(value: unknown, code = 200) {
  return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });
}

// A gateway that remembers the kiosk flag: PUT /v1/instance/kiosk changes what the next GET says.
function mount(opts: { token?: string; enabled?: boolean; refuse?: boolean; mock?: boolean } = {}) {
  const token = opts.token ?? 'owner-demo';
  let enabled = opts.enabled ?? false;
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path !== '/v1/instance/kiosk') return response({ error: 'not_found', message: 'no' }, 404);
    if (opts.refuse) return response({ error: 'permission_denied', message: 'only an owner may change the box screen' }, 403);
    if (method === 'PUT') enabled = JSON.parse(String(init?.body)).enabled;
    return response({ enabled, apply: "The box's own screen switches within a few seconds." });
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(
    <MemoryRouter initialEntries={['/settings/appearance']}>
      <SessionProvider deps={{ mock: opts.mock ?? false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}>
        <App mock={opts.mock ?? false} />
      </SessionProvider>
    </MemoryRouter>,
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

it('shows the box screen as off and turns it on with a PUT, then shows what the box now says', async () => {
  const calls = mount();
  expect(await screen.findByText(/Off: the monitor plugged into this box shows the plain text screen/)).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Turn the box screen on' }));
  expect(await screen.findByText(/On: the monitor plugged into this box shows the dashboard full screen/)).toBeInTheDocument();
  expect(calls.filter((c) => c.method === 'PUT')).toEqual([{ method: 'PUT', path: '/v1/instance/kiosk', body: { enabled: true } }]);
  expect(screen.getByRole('button', { name: 'Turn the box screen off' })).toBeInTheDocument();
});

it('turns it off again from the on state', async () => {
  const calls = mount({ enabled: true });
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Turn the box screen off' }));
  expect(await screen.findByText(/Off: the monitor/)).toBeInTheDocument();
  expect(calls.filter((c) => c.method === 'PUT')[0]?.body).toEqual({ enabled: false });
});

it('shows nothing when the gateway says the person is not an owner', async () => {
  mount({ refuse: true });
  expect(await screen.findByRole('heading', { level: 1, name: 'Appearance' })).toBeInTheDocument();
  await vi.waitFor(() => expect(screen.queryByText("This box's screen")).not.toBeInTheDocument());
  expect(screen.queryByRole('button', { name: /box screen/ })).not.toBeInTheDocument();
});

it('never asks the gateway for an adult, and shows nothing in demo mode', async () => {
  const adult = mount({ token: 'adult-demo' });
  expect(await screen.findByRole('heading', { level: 1, name: 'Appearance' })).toBeInTheDocument();
  expect(adult).toHaveLength(0);
  expect(screen.queryByText("This box's screen")).not.toBeInTheDocument();
});

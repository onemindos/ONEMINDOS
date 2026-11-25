// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { seriousViolations } from '../test/helpers';
import { SettingsBusEvents } from './SettingsBusEvents';

// The shape of GET /v1/fabric/events (core/onemind_core/routers/fabric_events.py).
const watching = {
  observer: 'watching',
  events: [
    { seq: 9, ts: '2026-11-25T10:00:03Z', event: 'fabric.auth_failed', account: null, key: 'UCVXBA2UEXAMPLE', identity: null, client: 'client', name: null, cause: 'unknown_key', reason: 'Authentication Failure', repeats: 58 },
    { seq: 8, ts: '2026-11-25T10:00:00Z', event: 'fabric.connect', account: 'NODE_aaaa1111', key: 'UB6UKIVGEXAMPLE', identity: 'node:aaaa1111', client: 'leaf', name: 'leaf', cause: null, reason: null, repeats: null },
  ],
};

function response(value: unknown, code = 200) {
  return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } });
}

function mount(route: (path: string) => Response, mock = false) {
  const fetch = vi.fn(async (url: string | URL | Request) => {
    const u = new URL(String(url));
    return route(u.pathname + u.search);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  const utils = render(
    <MemoryRouter>
      <SessionProvider deps={{ mock, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}>
        <SettingsBusEvents />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { fetch, ...utils };
}
afterEach(() => vi.unstubAllGlobals());

it('lists who connected and who was refused, newest first, from GET /v1/fabric/events', async () => {
  const { fetch, container } = mount((p) => response(p.startsWith('/v1/fabric/events') ? watching : {}));
  const refused = await screen.findByRole('row', { name: /Refused/ });
  expect(within(refused).getByText('UCVXBA2U…')).toBeInTheDocument();
  expect(refused).toHaveTextContent('A key this box never issued · Authentication Failure (+58 more)');
  const joined = screen.getByRole('row', { name: /Connected/ });
  expect(joined).toHaveTextContent('node:aaaa1111');
  expect(joined).toHaveTextContent('account NODE_aaaa1111');
  expect(fetch.mock.calls.some(([u]) => String(u).endsWith('/v1/fabric/events?count=20'))).toBe(true);
  expect(await seriousViolations(container)).toEqual([]);
});

it('says so when the box has no observer key, and lists nothing', async () => {
  mount(() => response({ observer: 'off', events: [] }));
  expect(await screen.findByText(/does not watch the bus yet/)).toBeInTheDocument();
  expect(screen.queryByRole('table')).toBeNull();
});

it('warns when the observer is not connected', async () => {
  mount(() => response({ observer: 'connecting', events: [] }));
  expect(await screen.findByText(/observer is not connected/)).toBeInTheDocument();
  expect(screen.getByText('No bus events yet.')).toBeInTheDocument();
});

it('is not there for someone without audit:read', async () => {
  const { container } = mount(() => response({ error: 'permission_denied', message: 'no' }, 403));
  await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
});

it('shows nothing in demo mode and asks the hub nothing', () => {
  const { fetch, container } = mount(() => response({}), true);
  expect(container).toBeEmptyDOMElement();
  expect(fetch).not.toHaveBeenCalled();
});

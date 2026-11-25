// SPDX-License-Identifier: Apache-2.0
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { renderApp } from '../test/helpers';

function mount() {
  let status = 200;
  const queries: URLSearchParams[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), window.location.origin);
    if (url.pathname === '/v1/nodes') {
      return Response.json([{ node_id: 'node-1', hostname: 'Hallway', status: 'online', last_seen: new Date().toISOString() }]);
    }
    if (url.pathname === '/v1/series') {
      expect(init?.method).toBe('GET');
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer owner-demo');
      queries.push(url.searchParams);
      return status === 200
        ? Response.json([{ at: new Date().toISOString(), value: 25 }])
        : Response.json({ error: status === 401 ? 'unauthenticated' : status === 403 ? 'permission_denied' : 'unavailable', message: 'History unavailable' }, { status });
    }
    return Response.json({ error: 'not_found', message: 'No route in test fixture' }, { status: 404 });
  });
  vi.stubGlobal('fetch', fetch);
  renderApp({ token: 'owner-demo', mock: false, route: '/dashboards' });
  return { queries, respondWith: (next: number) => { status = next; } };
}

afterEach(() => vi.unstubAllGlobals());

it('opens the registered screen and requests history only for the selected gateway machine and metric', async () => {
  const { queries } = mount();
  const table = await screen.findByRole('table', { name: 'Processor readings in the last hour' });
  expect(within(table).getByRole('cell', { name: '25%' })).toBeVisible();
  expect(queries[0]?.toString()).toBe('node_id=node-1&metric=cpu_pct&window_s=3600&points=60');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Metric' }), 'temp_c');
  expect(await screen.findByRole('table', { name: 'Temperature readings in the last hour' })).toBeVisible();
  expect(queries[1]?.get('metric')).toBe('temp_c');
});

it.each([401, 403])('discarded readings stay hidden after HTTP %i and a subsequent outage', async (denied) => {
  const { queries, respondWith } = mount();
  expect(await screen.findByRole('table')).toBeVisible();
  const refresh = screen.getByRole('button', { name: 'Refresh history' });
  respondWith(denied);
  await userEvent.click(refresh);
  expect(await screen.findByText('Your account does not have access to this history.')).toBeVisible();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();

  respondWith(503);
  await userEvent.click(refresh);
  await waitFor(() => expect(queries).toHaveLength(3));
  expect(screen.getByText('Your account does not have access to this history.')).toBeVisible();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

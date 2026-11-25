// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { WorldSources } from './WorldSources';

const state = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('../session', () => ({
  useSignedIn: () => ({ token: 'fixture' }),
  useSession: () => ({ signOut: state.signOut }),
}));
afterEach(() => vi.unstubAllGlobals());

it('shows only licensed, attributed snapshots through the bridge read API', async () => {
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    expect(init.method).toBe('GET');
    expect(init.redirect).toBe('error');
    const path = new URL(url).pathname;
    if (path === '/v1/bridges') return Response.json([{ id: 'weather', provider: 'Weather service', state: 'active' }]);
    expect(path).toBe('/v1/bridges/weather/latest');
    const latest = { kind: 'alert', name: 'warning', field: 'state', revision: 1, received_at: '2026-01-01T00:00:00Z' };
    return Response.json([
      { ...latest, id: 'valid', datapoint: { value: { headline: 'Wind alert' }, licence: { attribution: 'Weather service' } } },
      { ...latest, id: 'unattributed', datapoint: { value: { headline: 'Hide this' } } },
      { ...latest, id: 'show-only', datapoint: null },
    ]);
  });
  vi.stubGlobal('fetch', fetch);
  render(<WorldSources />);
  await userEvent.click(await screen.findByRole('button', { name: /Weather service/ }));
  expect(await screen.findByText('Wind alert')).toBeVisible();
  expect(screen.getByText(/As of/)).toBeVisible();
  expect(screen.queryByText('Hide this')).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('shows a refusal instead of displaying a restricted source’s records', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new URL(url).pathname === '/v1/bridges'
    ? Response.json([{ id: 'private', provider: 'Private source', state: 'active' }])
    : Response.json({ error: 'permission_denied', message: 'Owner only' }, { status: 403 })));
  render(<WorldSources />);
  await userEvent.click(await screen.findByRole('button', { name: /Private source/ }));
  expect(await screen.findByText('Owner only')).toBeVisible();
});

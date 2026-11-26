// SPDX-License-Identifier: Apache-2.0
// Settings > Verification levels mounted the way main.tsx mounts it for a real hub: no knownPrincipal, so the
// session has no principal and the role comes only from GET /v1/me (review on #1246).
import { screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { renderApp } from '../test/helpers';

const table = { rows: [{ key: 'tier.T3', label: 'Approve a destructive action', default: 'L2', current: 'L2', minimum: 'L1', maximum: 'L3', strict: false }],
  types: [], household_level: 'L2', grace: false, recovery_needed: false, box_confirm: true };

function hub() {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    paths.push(path);
    if (path === '/v1/verification-requirements') return Response.json(table);
    if (path === '/v1/actions' || path === '/v1/users') return Response.json([]);
    return Response.json({ error: 'not_found', message: 'No route in test fixture' }, { status: 404 });
  }));
  return paths;
}
afterEach(() => vi.unstubAllGlobals());
const T = { timeout: 4000 };

it('opens for the owner on a real hub, where only GET /v1/me knows the role', async () => {
  hub();
  renderApp({ token: 'owner-demo', mock: false, knownRole: false, route: '/settings/verification' });
  expect(await screen.findByText('Approve a destructive action', undefined, T)).toBeVisible();
  expect(screen.queryByText(/Only an owner can see and change how strongly/)).toBeNull();
});

it('stays closed to a non-owner on a real hub and never reads the table', async () => {
  const paths = hub();
  renderApp({ token: 'adult-demo', mock: false, knownRole: false, route: '/settings/verification' });
  expect(await screen.findByText(/Only an owner can see and change how strongly/, undefined, T)).toBeVisible();
  expect(screen.queryByText('Approve a destructive action')).toBeNull();
  expect(paths).not.toContain('/v1/verification-requirements');
});

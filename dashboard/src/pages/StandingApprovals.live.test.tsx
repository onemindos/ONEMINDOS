// SPDX-License-Identifier: Apache-2.0
// Settings > Standing approvals mounted the way main.tsx mounts it for a real hub: no knownPrincipal, so the
// session has no principal and the role comes only from GET /v1/me (review on #1265).
import { screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { renderApp } from '../test/helpers';

const policy = { id: 'apol_1', revision: 1, name: 'Nightly restarts', allow: { types: ['app.restart'], requested_by: ['agent:hermes'], params: {} },
  limits: { per_day: 3 }, window_id: null, expires_at: '2026-12-20T00:00:00Z', created_by: { kind: 'person', id: 'owner' }, created_at: '2026-11-20T00:00:00Z',
  state: 'active', uses_24h: 1 };

function hub() {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    paths.push(path);
    if (path === '/v1/approval-policies') return Response.json([policy]);
    if (path === '/v1/agents' || path === '/v1/automation/rules' || path === '/v1/windows') return Response.json([]);
    return Response.json({ error: 'not_found', message: 'No route in test fixture' }, { status: 404 });
  }));
  return paths;
}
afterEach(() => vi.unstubAllGlobals());
const T = { timeout: 4000 };

it('opens for the owner on a real hub, where only GET /v1/me knows the role', async () => {
  hub();
  renderApp({ token: 'owner-demo', mock: false, knownRole: false, route: '/settings/standing-approvals' });
  expect((await screen.findAllByText('Nightly restarts', undefined, T))[0]).toBeVisible();
  expect(screen.queryByText('Only an owner can see and change standing approvals.')).toBeNull();
});

it('stays closed to a non-owner on a real hub and never reads the standing approvals', async () => {
  const paths = hub();
  renderApp({ token: 'adult-demo', mock: false, knownRole: false, route: '/settings/standing-approvals' });
  expect(await screen.findByText('Only an owner can see and change standing approvals.', undefined, T)).toBeVisible();
  expect(screen.queryByText('Nightly restarts')).toBeNull();
  expect(paths).not.toContain('/v1/approval-policies');
});

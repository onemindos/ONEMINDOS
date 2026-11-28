// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const rule = { id: 'rule_1', name: 'Nightly backup check', enabled: true, trigger: { schedule: { cron: '0 3 * * *', tz: 'box' } }, actions: [{}], last_fired_at: '2026-11-19T03:00:00Z', breaker: null, failures: 0 };
const data: Record<string, unknown> = {
  '/v1/automation/state': { paused: false, changed_by: null, changed_at: '2026-11-01T00:00:00Z', reason: null },
  '/v1/automation/rules': [rule],
  '/v1/automation/schedules': [{ rule_id: 'rule_1', name: rule.name, enabled: true, cron: '0 3 * * *', tz: 'box', next_fire_at: '2026-11-20T03:00:00Z', next_match_at: '2026-11-20T03:00:00Z' }],
  '/v1/automation/runs': [{ id: 'run_1', rule_id: 'rule_1', revision: 1, fired_at: '2026-11-19T03:00:00Z', action_ids: [], outcome: 'filed' }],
};
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }
function mount(override?: (path: string) => Response) {
  const methods: string[] = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    methods.push(init?.method ?? 'GET');
    const path = new URL(String(url)).pathname;
    return override ? override(path) : response(data[path]);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/automation']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { fetch, methods };
}
afterEach(() => vi.unstubAllGlobals());

it('shows real rules, schedule, runs and kill switch, and only reads', async () => {
  const { fetch, methods } = mount();
  expect(await screen.findByRole('heading', { level: 1, name: 'Automation' })).toBeInTheDocument();
  expect(await screen.findByText('Nightly backup check')).toBeInTheDocument();
  expect(screen.getByText('On a schedule (0 3 * * *, box)')).toBeInTheDocument();
  expect(await screen.findByText(/^Automation is running\. Anything a rule files still needs approval unless you set a/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'standing approval' })).toHaveAttribute('href', '/settings/standing-approvals');
  expect(await screen.findByText(/Nightly backup check · 2026-11-19T03:00:00Z · filed/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /pause|resume|enable|disable|delete|create/i })).not.toBeInTheDocument();
  expect(fetch.mock.calls.every(([url]) => { const p = new URL(String(url)).pathname; return p.startsWith('/v1/automation') || p === '/v1/windows'; })).toBe(true);
  expect(methods.every((m) => m === 'GET')).toBe(true);
});

it('says plainly when automation is paused', async () => {
  mount((path) => response(path === '/v1/automation/state' ? { paused: true, reason: 'away', changed_at: 'x', changed_by: null } : data[path]));
  expect(await screen.findByText(/All automation is paused/)).toHaveTextContent('Reason: away');
});

it('keeps the last data and labels it stale when a refresh fails', async () => {
  let reads = 0;
  mount((path) => path === '/v1/automation/rules' && ++reads > 1 ? response({ error: 'unavailable', message: 'down' }, 503) : response(data[path]));
  expect(await screen.findByText('Nightly backup check')).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Refresh automation' }));
  await waitFor(() => expect(screen.getByText(/previously fetched automation data/)).toBeInTheDocument());
  expect(screen.getByText('Nightly backup check')).toBeInTheDocument();
});

it('handles a malformed list without crashing', async () => {
  mount((path) => response(path === '/v1/automation/rules' ? {} : data[path]));
  expect(await screen.findByText(/invalid automation list/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Automation' })).toBeInTheDocument();
});

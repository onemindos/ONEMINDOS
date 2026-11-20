// SPDX-License-Identifier: Apache-2.0
// NMD-07 (#132): Settings > Updates shows and edits the gateway's update policy via @onemind/sdk.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const knobs = { window_id: 'win_nightly', cool_off_hours: 48, same_major_only: true, backoff_after_failures: 3, ai_schedule: { enabled: false, tz: 'box', off: [{ days: ['mon'], start: '23:00', end: '07:00' }] } };
const policy = { ...knobs, customized: false, updated_at: null, updated_by: null, paused_apps: [{ app_id: 'whoami', failures: 3 }] };
const dry = {
  evaluated_at: '2026-11-11T22:00:00Z', at: '2026-11-12T02:00:00Z', automation_paused: false,
  window: { id: 'win_nightly', name: 'nightly', open_now: false, next_open_at: '2026-11-12T02:00:00Z' },
  apps: [
    { app_id: 'uptime-kuma', name: 'Uptime Kuma', from_version: '1.0.0', to_version: '1.0.1', kind: 'patch', released_at: null, outcome: 'would_update', reason: 'policy_ok', until: null },
    { app_id: 'whoami', name: 'whoami', from_version: '1.10.1', to_version: '2.0.0', kind: 'major', released_at: null, outcome: 'held', reason: 'major_update', until: null },
  ],
  ai: { enabled: false, off_now: false, next_change_at: null, apps: ['hermes-like'] },
};
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }

function mount(token: 'owner-demo' | 'adult-demo' = 'owner-demo') {
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/v1/update-policy/dry-run') return response(dry);
    if (path === '/v1/update-policy' && method === 'PUT') return response({ ...policy, ...JSON.parse(String(init!.body)), customized: true, updated_at: '2026-11-11T22:00:00Z' });
    if (path === '/v1/update-policy/resume') return response({ ...policy, paused_apps: [] });
    return response(policy);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/updates']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

it('shows the knobs, the paused apps and what would update tonight from the gateway', async () => {
  const calls = mount();
  expect(await screen.findByLabelText('Cool-off after a release (hours)')).toHaveValue(48);
  expect(screen.getByLabelText('Same major version only')).toBeChecked();
  expect(screen.getByText(/3 failed updates in a row/)).toBeInTheDocument();
  expect(await screen.findByText('Uptime Kuma')).toBeInTheDocument();
  expect(screen.getByText('Would update')).toBeInTheDocument();
  expect(screen.getByText(/New major version: only a person updates it/)).toBeInTheDocument();
  expect(screen.getByText(/Covers: hermes-like/)).toBeInTheDocument();
  expect(calls.every((c) => c.path.startsWith('/v1/update-policy'))).toBe(true);
});

it('saves the edited knobs with PUT and lifts a back-off with resume', async () => {
  const calls = mount();
  const u = userEvent.setup();
  const cool = await screen.findByLabelText('Cool-off after a release (hours)');
  await u.clear(cool);
  await u.type(cool, '12');
  await u.click(screen.getByLabelText('Turn AI apps off on a schedule'));
  await u.click(screen.getByRole('button', { name: 'Save update policy' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true));
  const put = calls.find((c) => c.method === 'PUT')!.body as typeof knobs;
  expect(put.cool_off_hours).toBe(12);
  expect(put.ai_schedule.enabled).toBe(true);
  expect(put.ai_schedule.off[0]).toEqual({ days: ['mon'], start: '23:00', end: '07:00' });
  expect(put).not.toHaveProperty('paused_apps');
  await u.click(screen.getByRole('button', { name: 'Resume whoami' }));
  await waitFor(() => expect(calls.some((c) => c.path === '/v1/update-policy/resume' && (c.body as { app_id: string }).app_id === 'whoami')).toBe(true));
});

it('lets a non-owner read the policy but not change it', async () => {
  mount('adult-demo');
  expect(await screen.findByText('Only the owner can change these rules.')).toBeInTheDocument();
  expect(await screen.findByLabelText('Cool-off after a release (hours)')).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Save update policy' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Resume whoami' })).not.toBeInTheDocument();
});

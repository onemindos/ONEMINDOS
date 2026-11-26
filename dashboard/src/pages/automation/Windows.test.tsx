// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

function mount(token: string) {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/automation']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const win = { id: 'win_nightly', name: 'Nightly', tz: 'box', open_now: false, updated_at: '2026-11-26T00:00:00Z', ranges: [{ days: ['mon', 'tue'], start: '22:00', end: '06:00' }] };
function gateway(puts: { path: string; body: Record<string, unknown> }[], putAnswer: () => Response = () => json({ ...win, name: 'Late' })) {
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (path === '/v1/windows' && (init?.method ?? 'GET') === 'GET') return json([win]);
    if (path === '/v1/windows/win_nightly' && init?.method === 'PUT') { puts.push({ path, body: JSON.parse(String(init.body)) }); return putAnswer(); }
    if (path === '/v1/windows/win_garden' && init?.method === 'PUT') { puts.push({ path, body: JSON.parse(String(init.body)) }); return json({ ...win, id: 'win_garden' }); }
    if (path === '/v1/automation/state') return json({ paused: false });
    if (path.startsWith('/v1/automation/')) return json([]);
    return json({ error: 'not_found', message: path }, 404);
  }));
}
afterEach(() => vi.unstubAllGlobals());

it('shows each window in plain words, and an owner edits its name and a day', async () => {
  const puts: { path: string; body: Record<string, unknown> }[] = [];
  gateway(puts);
  mount('owner-demo');
  const u = userEvent.setup();
  expect(await screen.findByText('Mon, Tue, 22:00 to 06:00 (into the next morning)')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Edit Nightly' }));
  const name = screen.getByLabelText('Name');
  await u.clear(name); await u.type(name, 'Late');
  await u.click(screen.getByLabelText('Wednesday'));
  await u.click(screen.getByRole('button', { name: 'Save window' }));
  expect(await screen.findByText(/Saved "Late"/)).toBeInTheDocument();
  expect(puts).toEqual([{ path: '/v1/windows/win_nightly', body: { name: 'Late', tz: 'box', ranges: [{ days: ['mon', 'tue', 'wed'], start: '22:00', end: '06:00' }] } }]);
});

it('adds a new window with an id made from its name', async () => {
  const puts: { path: string; body: Record<string, unknown> }[] = [];
  gateway(puts);
  mount('owner-demo');
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Add a window' }));
  await u.type(screen.getByLabelText('Name'), 'Garden');
  expect(screen.getByText('Its id will be win_garden.')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: 'Save window' }));
  await screen.findByText(/Saved "Garden"/);
  expect(puts[0]!.path).toBe('/v1/windows/win_garden');
});

it('refuses a range whose start equals its end before anything is sent', async () => {
  const puts: { path: string; body: Record<string, unknown> }[] = [];
  gateway(puts);
  mount('owner-demo');
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit Nightly' }));
  const end = screen.getByLabelText('To');
  await u.clear(end); await u.type(end, '22:00');
  await u.click(screen.getByRole('button', { name: 'Save window' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/different end time/);
  expect(puts).toHaveLength(0);
});

it('explains the passkey step-up and keeps the edits', async () => {
  gateway([], () => json({ error: 'unauthenticated', message: 'sign in again with your passkey to do this', reason: 'step_up_required' }, 401));
  mount('owner-demo');
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Edit Nightly' }));
  await u.click(screen.getByRole('button', { name: 'Save window' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/needs your passkey/);
  expect(screen.getByLabelText('Name')).toHaveValue('Nightly');
});

it('shows windows read-only to anyone but an owner', async () => {
  gateway([]);
  mount('adult-demo');
  expect(await screen.findByText('Nightly')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit Nightly' })).not.toBeInTheDocument();
  expect(screen.getByText('Only an owner can change a window.')).toBeInTheDocument();
});

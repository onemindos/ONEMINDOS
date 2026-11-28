// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

function mount(token: string) {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/settings/agents']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
function response(body: unknown, code = 200) { return new Response(JSON.stringify(body), { status: code, headers: { 'content-type': 'application/json' } }); }
function gateway(deliveryPending = false) {
  let state: Record<string, unknown> = { on: false, changed_by: null, changed_at: null, reason: null };
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (path !== '/v1/agents/kill-switch') return response({ error: 'not_found', message: path }, 404);
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body));
      state = { on: body.on, changed_by: { id: 'owner', kind: 'person', role: 'owner' }, changed_at: '2026-11-18T12:00:00Z', reason: body.reason ?? null };
      if (deliveryPending) return response({ error: 'unavailable', message: 'Fabric policy enforcement is still pending.', reason: 'fabric_policy_pending' }, 503);
    }
    return response(state);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

it('lets the owner stop and resume every agent, with a confirmation and a reason', async () => {
  const fetch = gateway();
  mount('owner-demo');
  const card = await screen.findByRole('article', { name: 'Agent kill switch' });
  expect(await within(card).findByText('Agent requests allowed at the hub')).toBeInTheDocument();
  const u = userEvent.setup();
  await u.click(within(card).getByRole('button', { name: 'Stop all AI agents' }));
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'PUT')).toHaveLength(0); // nothing before the confirmation
  await u.type(screen.getByLabelText('Reason (for the audit record)'), 'agent misbehaving');
  await u.click(screen.getByRole('button', { name: 'Stop agents' }));
  expect(await within(card).findByText('Agent requests blocked at the hub')).toBeInTheDocument();
  const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')!;
  expect(JSON.parse(String(put[1]!.body))).toEqual({ on: true, reason: 'agent misbehaving' });
  expect(new Headers(put[1]!.headers).get('authorization')).toBe('Bearer owner-demo');
  expect(within(card).getByText(/agent misbehaving/)).toBeInTheDocument();
  await u.click(within(card).getByRole('button', { name: 'Resume AI agents' }));
  await u.click(screen.getByRole('button', { name: 'Resume agents' }));
  await waitFor(() => expect(within(card).getByText('Agent requests allowed at the hub')).toBeInTheDocument());
});

it('refreshes the hub switch immediately and reports that fabric confirmation is pending after 503', async () => {
  const fetch = gateway(true);
  mount('owner-demo');
  const card = within(await screen.findByRole('article', { name: 'Agent kill switch' }));
  const user = userEvent.setup();
  await user.click(await card.findByRole('button', { name: 'Stop all AI agents' }));
  await user.click(screen.getByRole('button', { name: 'Stop agents' }));
  expect(await card.findByRole('alert')).toHaveTextContent('Fabric confirmation was pending');
  expect(await card.findByText('Agent requests blocked at the hub')).toBeVisible();
  const switchCalls = fetch.mock.calls.filter(([url]) => String(url).endsWith('/v1/agents/kill-switch'));
  expect(switchCalls.map((call) => call[1]?.method)).toEqual(['GET', 'PUT', 'GET']);
});

it('shows the state to a non-owner without offering the switch', async () => {
  gateway();
  mount('adult-demo');
  const card = await screen.findByRole('article', { name: 'Agent kill switch' });
  expect(await within(card).findByText('Agent requests allowed at the hub')).toBeInTheDocument();
  expect(within(card).queryByRole('button', { name: 'Stop all AI agents' })).not.toBeInTheDocument();
  expect(within(card).getByText('Only the owner can stop or resume agents.')).toBeInTheDocument();
});

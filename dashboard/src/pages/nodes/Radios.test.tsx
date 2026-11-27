// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

function mount(token: string) {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/nodes']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const card = (confirmed: boolean) => ({ id: 'abc123.lora0', node_id: 'abc123', node_status: 'online', hostname: 'garage', kind: 'lora', model: 'T-Beam', match: 'x', tty: '/dev/ttyACM0', device: '/dev/onemind/lora0', usb_id: '303a:1001', usb_port: '1-1',
  confirm: { profile: 'meshcore-companion-usb', label: 'MeshCore companion (USB)', confirmed, confirmed_at: confirmed ? '2026-11-26T10:00:00Z' : null } });
function gateway(state: { confirmed: boolean }, posts: { path: string; body: unknown }[], confirmStatus = 200) {
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (path === '/v1/radios') return json([card(state.confirmed)]);
    if (path === '/v1/radios/abc123.lora0/confirm' && init?.method === 'POST') {
      posts.push({ path, body: JSON.parse(String(init.body)) });
      if (confirmStatus !== 200) return json({ error: 'conflict', message: 'the machine is not online' }, confirmStatus);
      state.confirmed = true;
      return json(card(true));
    }
    return json({ error: 'not_found', message: path }, 404);
  }));
}
afterEach(() => vi.unstubAllGlobals());

it('lets an owner confirm a found radio after reading what it means, then shows it confirmed', async () => {
  const posts: { path: string; body: unknown }[] = [];
  gateway({ confirmed: false }, posts);
  mount('owner-demo');
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Confirm what this is' }));
  expect(posts).toHaveLength(0); // opening the question sends nothing
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent(/Only you can say/);
  await u.click(within(dialog).getByRole('button', { name: 'Yes, confirm' }));
  expect(await screen.findByText(/Confirmed as MeshCore companion \(USB\)/)).toBeInTheDocument();
  expect(posts).toEqual([{ path: '/v1/radios/abc123.lora0/confirm', body: { profile: 'meshcore-companion-usb' } }]);
});

it('offers no confirm button to anyone but an owner', async () => {
  gateway({ confirmed: false }, []);
  mount('adult-demo');
  expect(await screen.findByText(/Only an owner can confirm what a radio is/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Confirm what this is' })).not.toBeInTheDocument();
});

it('says why when the machine is offline (409)', async () => {
  gateway({ confirmed: false }, [], 409);
  mount('owner-demo');
  const u = userEvent.setup();
  await u.click(await screen.findByRole('button', { name: 'Confirm what this is' }));
  await u.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Yes, confirm' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/machine is not online/);
});

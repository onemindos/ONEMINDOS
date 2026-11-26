// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { holds, MyDevices } from './MyDevices';

const state = vi.hoisted(() => ({ mock: false }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: state.mock }), useSession: () => ({ signOut: vi.fn() }) }));
afterEach(() => { vi.unstubAllGlobals(); state.mock = false; });

const cred = (source: string, id: string) => ({ source, id, label: 'x', detail: '', created_at: null, last_seen_at: null });
const laptop = { id: 'dev_laptop', label: 'Work laptop', kind: 'browser', current: true, last_seen_at: new Date().toISOString(), first_seen_at: null, credentials: [cred('sessions', 's1')] };
const phone = { id: 'dev_phone', label: 'Pixel 9', kind: 'phone', current: false, last_seen_at: null, first_seen_at: null,
  credentials: [cred('sessions', 's2'), cred('sessions', 's3'), cred('passkeys', 'pk1'), cred('push', 'p1')] };
const sources = { sessions: true, passkeys: true, approver_keys: true, push: true, mesh: false, nats: false };

// A gateway with the two routes of core/onemind_core/routers/devices_me.py.
function gateway(remove: () => Response = () => Response.json({ id: 'dev_phone', removed: true, revoked: { sessions: 2, passkeys: 1, approver_keys: 0, push: 1 } })) {
  let devices = [laptop, phone];
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    calls.push(`${init?.method ?? 'GET'} ${path}`);
    if (path === '/v1/me/devices') return Response.json({ devices, sources });
    if (path === '/v1/me/devices/dev_phone' && init?.method === 'DELETE') {
      const r = remove();
      if (r.ok) devices = [laptop];
      return r;
    }
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
  return calls;
}

it('says what each device holds, in words', () => {
  expect(holds(phone as never)).toBe('2 sign-ins, 1 passkey, 1 push registration');
  expect(holds({ credentials: [] })).toBe('nothing');
});

it('lists your devices and never offers to remove the one in use', async () => {
  gateway();
  render(<MyDevices />);
  expect(await screen.findByText('Pixel 9')).toBeInTheDocument();
  expect(screen.getByText('In use here')).toBeInTheDocument();
  expect(screen.getByText('2 sign-ins, 1 passkey, 1 push registration')).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /Lost this device/ })).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Lost this device: Pixel 9' })).toBeInTheDocument();
});

it('removes a lost device only after a second click and says what was revoked', async () => {
  const calls = gateway();
  const user = userEvent.setup();
  render(<MyDevices />);
  await user.click(await screen.findByRole('button', { name: 'Lost this device: Pixel 9' }));
  expect(calls.some((c) => c.startsWith('DELETE'))).toBe(false);
  const confirm = within(screen.getByRole('group', { name: 'Remove Pixel 9?' }));
  await user.click(confirm.getByRole('button', { name: 'Remove Pixel 9' }));
  expect(await screen.findByText(/Pixel 9 is removed: 4 credentials revoked/)).toBeInTheDocument();
  expect(calls).toContain('DELETE /v1/me/devices/dev_phone');
  expect(screen.queryByRole('button', { name: 'Lost this device: Pixel 9' })).toBeNull();
});

it('explains the passkey step-up in plain words', async () => {
  gateway(() => Response.json({ error: 'unauthenticated', message: 'sign in again with your passkey to do this', reason: 'step_up_required' }, { status: 401 }));
  const user = userEvent.setup();
  render(<MyDevices />);
  await user.click(await screen.findByRole('button', { name: 'Lost this device: Pixel 9' }));
  await user.click(screen.getByRole('button', { name: 'Remove Pixel 9' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('needs a fresh passkey sign-in');
  expect(screen.getByText('Pixel 9')).toBeInTheDocument();
});

it('keeping the device sends nothing', async () => {
  const calls = gateway();
  const user = userEvent.setup();
  render(<MyDevices />);
  await user.click(await screen.findByRole('button', { name: 'Lost this device: Pixel 9' }));
  await user.click(screen.getByRole('button', { name: 'Keep it' }));
  expect(screen.getByRole('button', { name: 'Lost this device: Pixel 9' })).toBeInTheDocument();
  expect(calls.every((c) => c.startsWith('GET'))).toBe(true);
});

it('calls nothing in demo mode', () => {
  state.mock = true;
  const calls = gateway();
  render(<MyDevices />);
  expect(screen.getByText(/Demo mode lists none/)).toBeInTheDocument();
  expect(calls).toEqual([]);
});

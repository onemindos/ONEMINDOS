// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { SettingsRegion } from './SettingsRegion';

const state = vi.hoisted(() => ({ role: 'owner', signOut: vi.fn() }));
vi.mock('../shell/Shell', () => ({ useShell: () => ({ role: state.role }) }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture' }), useSession: () => ({ signOut: state.signOut }) }));

afterEach(() => vi.unstubAllGlobals());

const VIEW = {
  available: true, seeded: false, dropped: 0,
  current: { model: 'pc105', layout: 'us', variant: '', options: '' },
  layouts: [
    { id: 'us', name: 'English (US)', variants: [{ id: 'dvorak', name: 'English (Dvorak)' }] },
    { id: 'de', name: 'German', variants: [{ id: 'nodeadkeys', name: 'German (no dead keys)' }] },
    { id: 'fr', name: 'French', variants: [] },
  ],
};

function gateway(view: unknown = VIEW, post?: (body: unknown) => Response) {
  const request = vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/system/keyboard' && init.method === 'GET') return Response.json(view);
    if (path === '/v1/system/keyboard' && init.method === 'POST') {
      const body = JSON.parse(String(init.body));
      return post ? post(body) : Response.json({ id: 'act-5', type: 'system.set_keymap', state: 'awaiting_approval', params: body }, { status: 202 });
    }
    throw new Error(`Unexpected test route ${init.method} ${path}`);
  });
  vi.stubGlobal('fetch', request);
  return request;
}

const posts = (request: ReturnType<typeof gateway>) => request.mock.calls.filter((c) => c[1].method === 'POST');

it('shows the layout the box uses and asks for a German no-dead-keys layout without approving it', async () => {
  state.role = 'owner';
  const net = gateway();
  render(<MemoryRouter><SettingsRegion /></MemoryRouter>);
  expect(await screen.findByText('English (US)', { selector: 'dd' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Ask to change keyboard' })).toBeDisabled(); // nothing changed yet
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText('Layout'), 'de');
  await user.selectOptions(await screen.findByLabelText('Variant'), 'nodeadkeys');
  await user.click(screen.getByRole('button', { name: 'Ask to change keyboard' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Asked for German (no dead keys).');
  expect(screen.getByRole('link', { name: 'Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-5');
  const sent = posts(net);
  expect(sent).toHaveLength(1);
  expect(JSON.parse(String(sent[0]![1].body))).toMatchObject({ layout: 'de', variant: 'nodeadkeys' });
  expect(net.mock.calls.some((c) => String(c[0]).includes('/approve'))).toBe(false);
});

it('offers no variant list for a layout without variants and sends no variant', async () => {
  state.role = 'owner';
  const net = gateway();
  render(<MemoryRouter><SettingsRegion /></MemoryRouter>);
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('Layout'), 'fr');
  expect(screen.queryByLabelText('Variant')).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Ask to change keyboard' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Asked for French.');
  expect(JSON.parse(String(posts(net)[0]![1].body))).toEqual({ layout: 'fr', reason: 'Asked in Settings > Language & region' });
});

it('says plainly when the box does not offer the layout', async () => {
  state.role = 'owner';
  gateway(VIEW, () => Response.json({ error: 'not_found', message: 'this image does not offer that keyboard layout' }, { status: 404 }));
  render(<MemoryRouter><SettingsRegion /></MemoryRouter>);
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('Layout'), 'fr');
  await user.click(screen.getByRole('button', { name: 'Ask to change keyboard' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This box does not offer that layout.');
});

it('marks the default while nothing is chosen, and says so when the box cannot be reached', async () => {
  state.role = 'owner';
  gateway({ ...VIEW, seeded: true });
  const first = render(<MemoryRouter><SettingsRegion /></MemoryRouter>);
  expect(await screen.findByText(/nothing chosen yet/)).toBeVisible();
  first.unmount();
  gateway({ available: false, reason: 'host_service_unreachable', message: 'the host service is not reachable', layouts: [] });
  render(<MemoryRouter><SettingsRegion /></MemoryRouter>);
  expect(await screen.findByRole('alert')).toHaveTextContent('the host service is not reachable');
  expect(screen.queryByRole('button', { name: 'Ask to change keyboard' })).toBeNull();
});

it('offers a nonowner nothing and never calls the box', async () => {
  state.role = 'adult';
  const net = gateway();
  render(<MemoryRouter><SettingsRegion /></MemoryRouter>);
  expect(await screen.findByText(/Only an owner can see or change/)).toBeVisible();
  expect(screen.queryByLabelText('Layout')).toBeNull();
  expect(net).not.toHaveBeenCalled();
});

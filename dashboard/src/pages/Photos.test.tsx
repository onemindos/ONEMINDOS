// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { dayOf } from './Photos';

const page1 = { items: [
  { id: 'ast_1', file_name: 'IMG_1.JPG', taken_at: '2026-05-02T12:00:00Z', size: 2_500_000, level: 'in_verified_backup' },
  { id: 'ast_2', file_name: 'IMG_2.JPG', taken_at: '2026-05-02T13:00:00Z', size: 900, level: 'on_box' },
  { id: 'ast_3', file_name: 'IMG_3.HEIC', taken_at: '2026-03-01T12:00:00Z', size: 500_000, level: 'in_backup' },
], next_cursor: 'cur1' };
const page2 = { items: [{ id: 'ast_4', file_name: 'OLD.JPG', taken_at: '2025-01-01T12:00:00Z', size: 100_000, level: 'on_box' }], next_cursor: null };
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } });

function mount(over?: (url: URL) => Response | undefined, who = 'owner-demo') {
  const fetch = vi.fn(async (input: string | URL | Request) => {
    const url = new URL(String(input), 'http://hub.test');
    const custom = over?.(url);
    if (custom) return custom;
    if (url.pathname === '/v1/photos/library') return json(url.searchParams.get('cursor') === 'cur1' ? page2 : page1);
    if (url.pathname.endsWith('/content')) return new Response('x', { headers: { 'content-type': url.pathname.includes('ast_3') ? 'application/octet-stream' : 'image/jpeg' } });
    return json({});
  });
  vi.stubGlobal('fetch', fetch);
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:photo', revokeObjectURL: () => undefined }));
  window.sessionStorage.setItem('onemind.token', who);
  render(<MemoryRouter initialEntries={['/photos']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(who), knownPrincipal: () => DEMO_TOKENS[who] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('shows the real library by day and says which photos are safe in a checked backup', async () => {
  const fetch = mount();
  expect(await screen.findByRole('heading', { level: 1, name: 'Photos' })).toBeInTheDocument();
  const day = await screen.findByRole('region', { name: dayOf(page1.items[0]!.taken_at) });
  expect(within(day).getAllByRole('button')).toHaveLength(2);
  expect(screen.getByRole('button', { name: 'Open IMG_3.HEIC' })).toBeInTheDocument();
  expect(fetch.mock.calls.every(([u]) => new URL(String(u), 'http://hub.test').pathname.startsWith('/v1/photos/'))).toBe(true);
  expect(screen.queryByRole('button', { name: /delete|remove|trash/i })).not.toBeInTheDocument();
});

it('opens a photo large with its safety, and falls back honestly for a file the browser cannot draw', async () => {
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Open IMG_1.JPG' }));
  const dialog = await screen.findByRole('dialog', { name: 'IMG_1.JPG' });
  expect(await within(dialog).findByRole('img', { name: 'IMG_1.JPG' })).toBeInTheDocument();
  expect(within(dialog).getByText('Safe in a checked backup')).toBeInTheDocument();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: 'Open IMG_3.HEIC' }));
  const heic = await screen.findByRole('dialog', { name: 'IMG_3.HEIC' });
  expect(await within(heic).findByText(/cannot show this file/)).toBeInTheDocument();
  expect(within(heic).getByText('In a backup, not checked yet')).toBeInTheDocument();
});

it('pages older photos with the cursor the hub gave', async () => {
  const fetch = mount();
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Show older photos' }));
  expect(await screen.findByRole('button', { name: 'Open OLD.JPG' })).toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => String(u).includes('cursor=cur1'))).toBe(true);
  expect(screen.queryByRole('button', { name: 'Show older photos' })).not.toBeInTheDocument();
});

it('says why when Photos is off or the account has no library, and when the library is empty', async () => {
  mount(() => json({ error: 'not_found', message: 'off' }, 404));
  expect(await screen.findByText('Photos is not turned on on this box.')).toBeInTheDocument();
});

it('invites a backup when the library is empty', async () => {
  mount((u) => (u.pathname === '/v1/photos/library' ? json({ items: [], next_cursor: null }) : undefined));
  await waitFor(() => expect(screen.getByText(/No photos yet/)).toBeInTheDocument());
});

// #1232: Photos is in every person's dock and shows their own library (the hub scopes it to the caller).
it.each(['adult-demo', 'teen-demo', 'child-demo'])('shows %s their own library and reads only photo routes', async (who) => {
  const fetch = mount(undefined, who);
  expect(await screen.findByRole('button', { name: 'Open IMG_1.JPG' })).toBeInTheDocument();
  expect(screen.queryByText(/does not have a photo library/)).not.toBeInTheDocument();
  expect(fetch.mock.calls.every(([u]) => new URL(String(u), 'http://hub.test').pathname.startsWith('/v1/photos/'))).toBe(true);
});

it('tells a guest plainly that they have no photo library when the hub says so', async () => {
  mount((url) => url.pathname === '/v1/photos/library' ? json({ error: 'permission_denied', message: 'no' }, 403) : undefined, 'guest-demo');
  expect(await screen.findByText(/Your account does not have a photo library/)).toBeInTheDocument();
});

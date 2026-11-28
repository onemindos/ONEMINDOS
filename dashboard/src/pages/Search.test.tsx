// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const token = 'owner-demo';
function mount() {
  window.sessionStorage.setItem('onemind.token', token);
  return render(<MemoryRouter initialEntries={['/search']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
function gateway(answer: (url: URL) => Response) {
  const fetch = vi.fn(async (url: string | URL | Request) => {
    const u = new URL(String(url));
    return u.pathname === '/v1/search' ? answer(u) : json({ error: 'not_found', message: u.pathname }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('searches the hub, groups the hits by kind and links them inside the app', async () => {
  const fetch = gateway(() => json([
    { provider: 'files', app_id: 'files', type: 'file', id: 'f1', title: 'Tax 2025.pdf', subtitle: 'Documents', link: 'onemind://app/files/browse/Documents' },
    { provider: 'settings', app_id: 'settings', type: 'setting', id: 's1', title: 'Backups', subtitle: null, link: 'onemind://app/settings/backups' },
  ]));
  mount();
  const u = userEvent.setup();
  await u.type(await screen.findByRole('searchbox', { name: 'What are you looking for?' }), 'tax');
  await u.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText('Tax 2025.pdf')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Files' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
  // Inside the Search window: the dock has its own Backups place.
  expect(within(screen.getByRole('region', { name: 'Search' })).getByRole('link', { name: 'Backups' })).toHaveAttribute('href', '/apps/settings/backups');
  expect(screen.getByText(/2 results for "tax"/)).toBeInTheDocument();
  const call = fetch.mock.calls.map(([url]) => new URL(String(url))).find((x) => x.pathname === '/v1/search')!;
  expect(call.searchParams.get('q')).toBe('tax');
  expect(fetch.mock.calls).toHaveLength(1); // a search is one read; nothing else is sent
});

it('says plainly when nothing matches', async () => {
  gateway(() => json([]));
  mount();
  const u = userEvent.setup();
  await u.type(await screen.findByRole('searchbox'), 'zzz');
  await u.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText('Nothing found for "zzz"')).toBeInTheDocument();
});

it('explains a search index that is not ready (503) without a stack trace', async () => {
  gateway(() => json({ error: 'unavailable', message: 'index busy' }, 503));
  mount();
  const u = userEvent.setup();
  await u.type(await screen.findByRole('searchbox'), 'tax');
  await u.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/Search is not ready yet/);
});

// SPDX-License-Identifier: Apache-2.0
// NMD-02 (#127): the offline library page shows the download size before every change and only
// files a request (it never approves). Shapes follow core/routers/content.py.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { bytes } from './Library';

const HAM = 'stack_exchange/ham.stackexchange.com_en_all_2026-10.zim';
const view = {
  app: { id: 'kiwix', in_catalog: true, status: 'installed' },
  library: [{ path: 'wikipedia/wikipedia_en_climate-change_mini_2026-10.zim', name: 'wikipedia_en_climate-change', flavour: 'mini', date: '2026-10' }],
  packs: [{ id: 'radio', title: 'Ham radio and SDR', description: 'Amateur radio reference.', books: [{ name: 'ham.stackexchange.com_en_all', flavour: '', in_library: false }] }],
  pending_action_id: null,
  auto_update: { enabled: false, window_id: 'win_nightly', window_open: false, last_checked_at: null, last_result: null, last_action_id: null, last_download_bytes: null },
};
const plan = {
  zims_before: [view.library[0]!.path], zims_after: [view.library[0]!.path, HAM],
  downloads: [{ name: 'ham.stackexchange.com_en_all', flavour: '', title: 'Amateur Radio', language: 'eng', path: HAM, size_bytes: 77109248, issued: '2026-10-01' }],
  removed: [], download_bytes: 77109248, changed: true,
};
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }

function mount() {
  const sent: Array<{ method: string; path: string; body: unknown }> = [];
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    sent.push({ method, path, body });
    if (path === '/v1/content') return response(view);
    if (path === '/v1/content/plan') return response(plan);
    if (path === '/v1/content/changes') return response({ action: { id: 'act-1', type: 'app.configure', state: 'awaiting_approval' }, plan }, 201);
    return response({ error: 'not_found', message: 'no' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/library']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return sent;
}
afterEach(() => vi.unstubAllGlobals());

it('formats sizes in plain units', () => {
  expect(bytes(77109248)).toBe('77 MB');
  expect(bytes(1864210432)).toBe('1.9 GB');
  expect(bytes(12)).toBe('12 bytes');
});

it('shows the download size before filing a pack, and files a request with that size', async () => {
  const sent = mount();
  expect(await screen.findByRole('heading', { level: 1, name: 'Offline library' })).toBeInTheDocument();
  expect(await screen.findByText('wikipedia_en_climate-change')).toBeInTheDocument();
  const u = userEvent.setup();
  await u.click(within(screen.getByRole('article', { name: 'Ham radio and SDR' })).getByRole('button', { name: 'Show download size' }));
  const dialog = await screen.findByRole('alertdialog');
  expect(within(dialog).getByText('Download: 77 MB')).toBeInTheDocument();
  expect(sent.some((r) => r.path === '/v1/content/changes')).toBe(false); // nothing filed before the size is seen
  await u.click(within(dialog).getByRole('button', { name: /Request \(77 MB to download\)/ }));
  await waitFor(() => expect(screen.getByText(/Request act-1 filed/)).toBeInTheDocument());
  const change = sent.find((r) => r.path === '/v1/content/changes')!;
  expect(change.method).toBe('POST');
  expect(change.body).toMatchObject({ add: [{ name: 'ham.stackexchange.com_en_all', flavour: '' }], remove: [], download_bytes: 77109248 });
  expect(sent.some((r) => r.path.includes('/approve'))).toBe(false); // the page never approves
});

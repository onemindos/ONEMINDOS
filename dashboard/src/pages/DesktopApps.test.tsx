// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const OBS = 'md.obsidian.Obsidian';
const sandbox = ['no files of the box except one folder of its own', 'no home folder', 'no way back out to the box'];
const off = { service: { available: false, reason: 'flatpak_unavailable', message: 'This box cannot run desktop apps yet: no host.', remote: 'flathub', sandbox }, installed: [], stream: { app_id: 'desktop-apps', installed: false } };
const on = { ...off, service: { available: true, reason: null, message: null, remote: 'flathub', sandbox } };
const withApp = { ...on, installed: [{ app_id: OBS, name: 'Obsidian', version: '1.8.9', installed: true, update_available: true, folder: `/data/onemind/desktop-apps/${OBS}/files` }] };
const found = { results: [{ app_id: OBS, name: 'Obsidian', summary: 'Knowledge base', version: '1.8.9', installed: false }] };
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(route: (method: string, path: string, query: string, body: unknown) => Response, token = 'owner-demo') {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url));
    return route(init?.method ?? 'GET', u.pathname, u.search, init?.body ? JSON.parse(String(init.body)) : undefined);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/desktop-apps']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('says it is not available yet and offers nothing to press', async () => {
  mount(() => response(off));
  expect(await screen.findByRole('heading', { level: 1, name: 'Desktop apps' })).toBeInTheDocument();
  expect(await screen.findByRole('note')).toHaveTextContent('not available yet: This box cannot run desktop apps yet: no host.');
  expect(screen.queryByLabelText('Search Flathub')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Ask to / })).not.toBeInTheDocument();
});

it('searches Flathub and files an install request for the owner to approve', async () => {
  const sent: unknown[] = [];
  const asked: string[] = [];
  mount((method, path, query, body) => {
    if (method === 'POST' && path === '/v1/actions') { sent.push(body); return response({ id: 'act-4', state: 'awaiting_approval' }, 201); }
    if (path === '/v1/desktop-apps/search') { asked.push(query); return response(found); }
    return response(on);
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Search Flathub'), 'obsidian');
  await user.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText(/md\.obsidian\.Obsidian · 1\.8\.9 · Knowledge base/)).toBeInTheDocument();
  expect(asked).toEqual(['?q=obsidian']);
  await user.click(screen.getByRole('button', { name: 'Ask to install Obsidian' }));
  expect(await screen.findByText(/Request act-4 to install md\.obsidian\.Obsidian is waiting for an owner/)).toBeInTheDocument();
  expect(sent).toEqual([expect.objectContaining({ type: 'desktop.app.install', params: { app_id: OBS } })]);
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-4');
});

it('lists installed apps with their folder and requests updates, removals and launches', async () => {
  const sent: string[] = [];
  mount((method, path, _q, body) => {
    if (method === 'POST' && path === '/v1/actions') { sent.push((body as { type: string }).type); return response({ id: 'act-5', state: 'awaiting_approval' }, 201); }
    if (method === 'POST' && path === `/v1/desktop-apps/${OBS}/launch`) { sent.push('launch'); return response({ id: 'act-6', state: 'awaiting_approval' }, 202); }
    return response(withApp);
  });
  const user = userEvent.setup();
  expect(await screen.findByText(`/data/onemind/desktop-apps/${OBS}/files`)).toBeInTheDocument();
  expect(screen.getByText(/update waiting/)).toBeInTheDocument();
  expect(screen.getByRole('note')).toHaveTextContent('one folder of its own; no home folder');
  await user.click(screen.getByRole('button', { name: 'Ask to update Obsidian' }));
  await screen.findByText(/to update .* is waiting/);
  await user.click(screen.getByRole('button', { name: 'Ask to remove Obsidian' }));
  await screen.findByText(/to remove .* is waiting/);
  await user.click(screen.getByRole('button', { name: 'Ask to launch Obsidian' }));
  expect(await screen.findByText(/Request act-6 to launch md\.obsidian\.Obsidian is waiting for an owner/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-6');
  expect(sent).toEqual(['desktop.app.update', 'desktop.app.remove', 'launch']);
});

it('shows a refusal from the box instead of failing silently', async () => {
  mount((method, path) => method === 'POST' && path === '/v1/actions'
    ? response({ error: 'policy_refused', reason: 'already_installed', message: `${OBS} is already installed.` }, 409) : response(withApp));
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Ask to remove Obsidian' }));
  expect(await screen.findByText(/Could not ask to remove: .*already installed/)).toBeInTheDocument();
});

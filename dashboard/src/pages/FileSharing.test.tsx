// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const people = [{ person_id: 'owner', role: 'owner', home: true }, { person_id: 'guest', role: 'guest', home: false }];
const off = { service: { available: false, reason: 'smb_unavailable', message: 'This box has no file-sharing service yet.', reach: ['lan', 'mesh'] }, people, shares: [] };
const on = { service: { available: true, reason: null, message: null, reach: ['lan', 'mesh'] }, people, shares: [] };
const shared = { ...on, shares: [{ id: 'shr_1', kind: 'home', person_id: 'owner', name: 'owner', root: 'home:owner', state: 'active', quota_bytes: null }] };
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(route: (method: string, path: string, body: unknown) => Response, token = 'owner-demo') {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    return route(init?.method ?? 'GET', path, init?.body ? JSON.parse(String(init.body)) : undefined);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/file-sharing']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('says it is not available yet and offers nothing to press', async () => {
  mount(() => response(off));
  expect(await screen.findByRole('heading', { level: 1, name: 'File sharing' })).toBeInTheDocument();
  expect(await screen.findByRole('note')).toHaveTextContent('not available yet: This box has no file-sharing service yet.');
  expect(screen.getByText('Nothing is shared.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Ask|Stop sharing/ })).not.toBeInTheDocument();
});

it('files a files.share.create request for the owner to approve, and only for people with files', async () => {
  const sent: unknown[] = [];
  const fetch = mount((method, path, body) => {
    if (method === 'POST' && path === '/v1/actions') { sent.push(body); return response({ id: 'act-9', type: 'files.share.create', state: 'awaiting_approval' }, 201); }
    return response(on);
  });
  const user = userEvent.setup();
  expect(screen.queryByText('guest')).not.toBeInTheDocument();
  await user.click(await screen.findByRole('button', { name: "Ask to share owner's files" }));
  expect(await screen.findByText(/Request act-9: awaiting_approval. Nothing is shared until an owner approves it/)).toBeInTheDocument();
  expect(sent).toEqual([expect.objectContaining({ type: 'files.share.create', params: { kind: 'home', person_id: 'owner' } })]);
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-9');
  await user.selectOptions(screen.getByLabelText('Time Machine size for owner'), '250');
  await user.click(screen.getByRole('button', { name: 'Ask for a Time Machine share for owner' }));
  await waitFor(() => expect(sent).toHaveLength(2));
  expect(sent[1]).toEqual(expect.objectContaining({ params: { kind: 'timemachine', person_id: 'owner', quota_bytes: 250 * 1024 ** 3 } }));
  expect(fetch.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === 'POST').map(([u]) => new URL(String(u)).pathname)).toEqual(['/v1/actions', '/v1/actions']);
});

it('lists shares and stops one only after a second click', async () => {
  let removed = false;
  const fetch = mount((method, path) => {
    if (method === 'POST' && path.endsWith('/stop')) { removed = true; return response({ removed: true, id: 'shr_1' }); }
    return response(removed ? on : shared);
  });
  const user = userEvent.setup();
  expect(await screen.findByText(/owner · owner's files · active/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Stop sharing owner' }));
  expect(fetch.mock.calls.some(([u]) => new URL(String(u)).pathname.endsWith('/stop'))).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Confirm stop sharing owner' }));
  expect(await screen.findByText('Nothing is shared.')).toBeInTheDocument();
  expect(fetch.mock.calls.map(([u]) => new URL(String(u)).pathname).filter((p) => p.endsWith('/stop'))).toEqual(['/v1/shares/smb/shr_1/stop']);
});

it('shows a refused request', async () => {
  mount((method) => method === 'POST' ? response({ error: 'policy_refused', message: 'owner already has this share (owner).' }, 409) : response(on));
  await userEvent.setup().click(await screen.findByRole('button', { name: "Ask to share owner's files" }));
  await waitFor(() => expect(screen.getByText(/Could not file the request: .*already has this share/)).toBeInTheDocument());
});

it('gives an adult no way to turn sharing on', async () => {
  mount(() => response({ ...on, people: [{ person_id: 'adult', role: 'adult', home: true }] }), 'adult-demo');
  expect(await screen.findByRole('note')).toHaveTextContent('An owner turns sharing on');
  expect(screen.queryByRole('button', { name: /Ask/ })).not.toBeInTheDocument();
});

it('reports an invalid payload honestly', async () => {
  mount(() => response({ service: 'x' }));
  expect(await screen.findByText(/invalid file sharing status/)).toBeInTheDocument();
});

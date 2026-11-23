// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const PW = '/v1/files/app-passwords';
const row = { id: 'apw_1', person_id: 'owner', username: 'owner', label: 'MacBook Finder', scopes: ['home:rw', 'shared:r'], created_at: '2026-11-22T10:00:00Z', last_used_at: null };
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }

function mount(route: (method: string, path: string, body: unknown) => Response | undefined, token = 'owner-demo', mock = false) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    return route(init?.method ?? 'GET', path, init?.body ? JSON.parse(String(init.body)) : undefined) ?? response({ error: 'not_found', message: 'no' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/account']}><SessionProvider deps={{ mock, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={mock} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('makes an app password with the chosen scopes and shows it once', async () => {
  const sent: unknown[] = [];
  let made = false;
  mount((method, path, body) => {
    if (path !== PW) return undefined;
    if (method === 'POST') { sent.push(body); made = true; return response({ ...row, password: 'abcd-efgh-jkmn-pqrs-tuvw', shown_once: true }, 201); }
    return response({ app_passwords: made ? [row] : [] });
  });
  const user = userEvent.setup();
  expect(await screen.findByText('No app passwords yet.')).toBeInTheDocument();
  expect(screen.getByText(/https:\/\/localhost\/dav\//)).toBeInTheDocument();
  const make = screen.getByRole('button', { name: 'Make an app password' });
  expect(make).toBeDisabled();
  await user.type(screen.getByLabelText('Device or app'), 'MacBook Finder');
  await user.selectOptions(screen.getByLabelText('Shared'), 'r');
  await user.click(make);
  expect(await screen.findByText(/It is shown once/)).toHaveTextContent('App password for MacBook Finder: user name owner, password abcd-efgh-jkmn-pqrs-tuvw.');
  expect(sent).toEqual([{ label: 'MacBook Finder', scopes: ['home:rw', 'shared:r'] }]);
  expect(await screen.findByText('My files read and write, Shared read only')).toBeInTheDocument();
});

it('revokes only after a second click', async () => {
  let revoked = false;
  const fetch = mount((method, path) => {
    if (method === 'DELETE' && path === `${PW}/apw_1`) { revoked = true; return response({ revoked: true, id: 'apw_1' }); }
    if (path === PW) return response({ app_passwords: revoked ? [] : [row] });
    return undefined;
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Revoke MacBook Finder' }));
  expect(fetch.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === 'DELETE')).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Confirm revoke MacBook Finder' }));
  expect(await screen.findByText('No app passwords yet.')).toBeInTheDocument();
  expect(revoked).toBe(true);
});

it('explains a step-up refusal instead of failing silently', async () => {
  mount((method, path) => {
    if (path !== PW) return undefined;
    if (method === 'POST') return response({ error: 'unauthenticated', message: 'sign in again with your passkey to do this', reason: 'step_up_required' }, 401);
    return response({ app_passwords: [] });
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Device or app'), 'Laptop');
  await user.click(screen.getByRole('button', { name: 'Make an app password' }));
  await waitFor(() => expect(screen.getByText(/Could not make the app password/)).toBeInTheDocument());
});

it('is not offered to a guest', async () => {
  const fetch = mount(() => undefined, 'guest-demo');
  await screen.findByRole('heading', { level: 1 });
  expect(screen.queryByText('App passwords')).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => String(u).includes(PW))).toBe(false);
});

it('says demo mode has none instead of showing made-up passwords', async () => {
  mount(() => undefined, 'owner-demo', true);
  expect(await screen.findByText(/Demo mode has none/)).toHaveAttribute('role', 'status');
});

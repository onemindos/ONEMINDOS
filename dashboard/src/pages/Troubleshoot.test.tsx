// SPDX-License-Identifier: Apache-2.0
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import type { components } from '@onemind/sdk';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { screensNav } from '../test/helpers';

const REASON = 'This version of OneMind cannot reach the host power controls yet.';
type Controls = components['schemas']['SystemControls'];
const controls = (pending: unknown[] = [], available = true): Controls => {
  const why = available ? null : REASON;
  return {
    controls: [
      { type: 'system.restart', label: 'Restart', risk: 'actuate', needs_passkey: false, confirm_phrase: null, available, unavailable_reason: why },
      { type: 'system.shutdown', label: 'Shut down', risk: 'actuate', needs_passkey: false, confirm_phrase: null, available, unavailable_reason: why },
      { type: 'system.factory_reset', label: 'Factory reset', risk: 'destructive', needs_passkey: true, confirm_phrase: 'factory reset', available, unavailable_reason: why },
    ],
    pending: pending as Controls['pending'],
  };
};
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }); }

function mount(route: (method: string, path: string, body: unknown) => Response, token = 'owner-demo') {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    return route(init?.method ?? 'GET', path, init?.body ? JSON.parse(String(init.body)) : undefined);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/troubleshoot']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('files a restart as a request and never shows a success', async () => {
  const posted: unknown[] = [];
  mount((method, path, body) => {
    if (method === 'POST' && path === '/v1/system/actions') { posted.push(body); return response({ id: 'act_1', type: 'system.restart', state: 'awaiting_approval' }, 202); }
    return response(controls(posted.length ? [{ id: 'act_1', type: 'system.restart', state: 'awaiting_approval' }] : []));
  });
  expect(await screen.findByRole('heading', { level: 1, name: 'Troubleshoot' })).toBeInTheDocument();
  expect(screen.queryByText('Not available on this box yet')).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Restart' }));
  await waitFor(() => expect(posted).toEqual([{ type: 'system.restart' }]));
  expect(await screen.findByRole('link', { name: 'Review in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_1');
  expect(screen.queryByText(/restarted|succeeded/i)).not.toBeInTheDocument();
});

it('asks for a factory reset only after the owner types the phrase', async () => {
  const posted: unknown[] = [];
  mount((method, _path, body) => {
    if (method === 'POST') { posted.push(body); return response({ id: 'act_2', type: 'system.factory_reset', state: 'awaiting_approval' }, 202); }
    return response(controls());
  });
  const button = await screen.findByRole('button', { name: 'Request factory reset' });
  expect(button).toBeDisabled();
  const u = userEvent.setup();
  await u.type(screen.getByLabelText(/Type "factory reset"/), 'factory reset');
  expect(button).toBeEnabled();
  await u.click(button);
  await waitFor(() => expect(posted).toEqual([{ type: 'system.factory_reset', confirm: 'factory reset' }]));
});

it('downloads the diagnostic bundle and shows what was removed', async () => {
  const create = vi.fn(() => 'blob:diag');
  Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  mount((_m, path) => path === '/v1/system/diagnostics'
    ? response({ schema: 'onemind.diagnostics/v1', redaction: { found: { email: 2, ipv4: 1 } } })
    : response(controls()));
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Download diagnostics' }));
  expect(await screen.findByText('Removed: 2 email, 1 ipv4.')).toBeInTheDocument();
  expect(create).toHaveBeenCalledOnce();
  expect(click).toHaveBeenCalledOnce();
  click.mockRestore();
});

it('says why a control is unavailable and disables it', async () => {
  const posted: unknown[] = [];
  mount((method, _path, body) => {
    if (method === 'POST') posted.push(body);
    return response(controls([], false));
  });
  expect(await screen.findByRole('button', { name: 'Restart' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Shut down' })).toBeDisabled();
  expect(screen.getAllByText('Not available on this box yet')).toHaveLength(2);
  expect(screen.getAllByText(REASON)).toHaveLength(2);
  const u = userEvent.setup();
  await u.type(screen.getByLabelText(/Type "factory reset"/), 'factory reset');
  expect(screen.getByRole('button', { name: 'Request factory reset' })).toBeDisabled();
  expect(posted).toEqual([]);
});

it('shows Troubleshoot in the menu to the owner only', async () => {
  mount(() => response(controls()));
  expect((await screensNav(userEvent.setup())).getAllByRole('link', { name: 'Troubleshoot' }).length).toBeGreaterThan(0);
  cleanup();
  mount(() => response({ error: 'permission_denied', message: 'only an owner may do this' }, 403), 'adult-demo');
  expect(await screen.findByText(/Your account is not allowed to see this/)).toBeInTheDocument();
  const nav = await screensNav(userEvent.setup());
  expect(nav.getAllByRole('link', { name: 'Backups' }).length).toBeGreaterThan(0);
  expect(nav.queryByRole('link', { name: 'Troubleshoot' })).not.toBeInTheDocument();
});

it('shows the owner-only refusal to everyone else', async () => {
  mount(() => response({ error: 'permission_denied', message: 'only an owner may do this' }, 403));
  expect(await screen.findByText(/Your account is not allowed to see this/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Restart' })).not.toBeInTheDocument();
});

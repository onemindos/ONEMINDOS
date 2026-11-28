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
afterEach(() => { vi.unstubAllGlobals(); lastLogUrl = ''; });

it('files a restart as a request and never shows a success', async () => {
  const posted: unknown[] = [];
  mount((method, path, body) => {
    if (method === 'POST' && path === '/v1/system/actions') { posted.push(body); return response({ id: 'act_1', type: 'system.restart', state: 'awaiting_approval' }, 202); }
    return response(controls(posted.length ? [{ id: 'act_1', type: 'system.restart', state: 'awaiting_approval' }] : []));
  });
  expect(await screen.findByRole('heading', { level: 1, name: 'Troubleshoot' })).toBeInTheDocument();
  expect(screen.queryByText('Not available on this box yet')).not.toBeInTheDocument();
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Restart' }));
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

let lastLogUrl = '';
function logRoute(body: (query: URLSearchParams) => Response) {
  return (_method: string, path: string) => path === '/v1/system/journal' ? body(new URLSearchParams(logQuery())) : response(controls());
}
const logQuery = () => new URL(lastLogUrl).search;

function mountLogs(token = 'owner-demo', body: (q: URLSearchParams) => Response = () => new Response('kernel: hello\nsshd: Accepted from [ip]\n', { status: 200, headers: { 'content-type': 'text/plain' } })) {
  const f = mount(logRoute(body), token);
  const inner = f.getMockImplementation()!;
  f.mockImplementation(async (url, init) => { if (String(url).includes('/v1/system/journal')) lastLogUrl = String(url); return inner(url, init); });
  return f;
}

it('reads the system journal with the chosen filters and shows the redacted lines as text', async () => {
  const f = mountLogs();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('tab', { name: 'Logs' }));
  await user.type(screen.getByLabelText(/Service/), 'sshd.service');
  await user.selectOptions(screen.getByLabelText('Level'), 'err');
  await user.selectOptions(screen.getByLabelText('Start'), '-1');
  await user.click(screen.getByRole('button', { name: 'Show logs' }));
  expect(await screen.findByLabelText('System log')).toHaveTextContent('kernel: hello sshd: Accepted from [ip]');
  const q = new URL(lastLogUrl).searchParams;
  expect(Object.fromEntries(q)).toEqual({ tail: '200', boot: '-1', unit: 'sshd.service', priority: 'err' });
  const call = f.mock.calls.find((c) => String(c[0]).includes('/v1/system/journal'))!;
  expect((call[1]!.headers as Record<string, string>).Authorization).toBe('Bearer owner-demo');
  expect(screen.getByRole('button', { name: 'Follow new lines' })).toBeDisabled(); // only this boot can be followed
});

it('does not send an invalid unit name and names every refusal in plain words', async () => {
  mountLogs('owner-demo', () => response({ error: 'rate_limited', message: 'too many', reason: 'limit_reached' }, 429));
  const user = userEvent.setup();
  await user.click(await screen.findByRole('tab', { name: 'Logs' }));
  await user.type(screen.getByLabelText(/Service/), 'sshd; rm');
  expect(screen.getByRole('button', { name: 'Show logs' })).toBeDisabled();
  expect(lastLogUrl).toBe('');
  await user.clear(screen.getByLabelText(/Service/));
  await user.click(screen.getByRole('button', { name: 'Show logs' }));
  expect(await screen.findByText(/Too many log reads/)).toBeInTheDocument();
});

it('strips terminal control characters from log lines and follows new lines until the stream ends', async () => {
  const sse = 'data: one \u001b[31mred\n\ndata: two\n\nevent: end\ndata: stream closed\n\n';
  mountLogs('owner-demo', (q) => q.has('follow') ? new Response(sse, { status: 200, headers: { 'content-type': 'text/event-stream' } })
    : new Response('plain \u001b[2Jline\n', { status: 200 }));
  const user = userEvent.setup();
  await user.click(await screen.findByRole('tab', { name: 'Logs' }));
  await user.click(screen.getByRole('button', { name: 'Show logs' }));
  expect((await screen.findByLabelText('System log')).textContent).toBe('plain [2Jline');
  await user.click(screen.getByRole('button', { name: 'Follow new lines' }));
  await waitFor(() => expect(screen.getByLabelText('System log').textContent).toBe('one [31mred\ntwo'));
  expect(new URL(lastLogUrl).searchParams.get('follow')).toBe('true');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Follow new lines' })).toBeEnabled());
});

it('offers no Logs tab to a person who is not the owner', async () => {
  mountLogs('adult-demo');
  expect(await screen.findByRole('heading', { level: 1, name: 'Troubleshoot' })).toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: 'Logs' })).not.toBeInTheDocument();
});

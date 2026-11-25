// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { HttpApi } from '../../api/client';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';
import * as credentials from '../../lib/webauthn';

const keys = ['alerts', 'approvals', 'apps', 'storage', 'backups', 'updates', 'mesh'];
const privateValues = ['node-private-7', 'testbox.example', ['person', 'example.invalid'].join('@'), '192.0.2.44', 'token-example-secret'];
const bundle = {
  schema: 'onemind.diagnostics/v1', gateway: { version: '0.1.0', hub_node_id: privateValues[0] },
  nodes: privateValues, redaction: { rules: ['email'], found: { email: 2 } }, future_field: privateValues,
};

function mount(token = 'owner-demo', version = '0.1.0') {
  let state = 'awaiting_approval';
  const action = () => ({ id: 'request-1', type: 'app.restart', state, params: { app_id: 'notes' },
    expires_at: '2099-01-01T00:00:00Z', plan_sha256: 'plan-a' });
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), location.origin).pathname;
    const method = init?.method ?? 'GET';
    calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const data = (() => {
      switch (path) {
        case '/v1/status':
          return Object.fromEntries(keys.map(k => [k, { state: k === 'storage' ? 'critical' : k === 'mesh' ? 'unknown' : 'ok', summary: privateValues[1] }]));
        case '/v1/alerts': return [{ id: 'alert-1', title: 'Notes needs a restart', state: 'open', fix: { type: 'app.restart' } }];
        case '/v1/alerts/alert-1/fix':
        case '/v1/actions/request-1': return action();
        case '/v1/actions/request-1/approve-options': return { publicKey: {}, plan_sha256: 'plan-a' };
        case '/v1/actions/request-1/approve': state = 'dispatched'; return { ...action(), state: 'succeeded' };
        case '/v1/system/controls': return { controls: [], pending: [] };
        case '/v1/system/diagnostics': return { ...bundle, gateway: { ...bundle.gateway, version } };
        default: throw Error('Unexpected request ' + path);
      }
    })();
    return new Response(JSON.stringify(data), { headers: { 'content-type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetch);
  const api = new MockApi(token);
  const real = new HttpApi({ token });
  const me = api.me.bind(api);
  Object.assign(api, { me: async () => ({ ...await me(), step_up: { passkeys_active: true, require_passkey_approval: true } }), approve: real.approve.bind(real), approveOptions: real.approveOptions.bind(real) });
  window.sessionStorage.setItem('onemind.token', token);
  const view = render(<MemoryRouter initialEntries={['/troubleshoot']}><SessionProvider deps={{ mock: false,
    knownPrincipal: t => DEMO_TOKENS[t], makeApi: () => api }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { ...view, calls };
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('files one fix, shows its pending action, and tracks actual progress after the human approves', async () => {
  const sign = vi.spyOn(credentials, 'getPasskey').mockResolvedValue({ id: 'signed-test-assertion' });
  const { calls } = mount();
  const user = userEvent.setup();
  const fix = await screen.findByRole('button', { name: 'Fix Notes needs a restart' });
  expect(screen.getByText(/mesh.*unknown/i)).toBeVisible();
  await user.click(fix);
  const fixRegion = screen.getByRole('region', { name: 'Fix a problem' });
  expect(await within(fixRegion).findByText('Awaiting approval')).toBeVisible();
  expect(calls.filter(c => c.method === 'POST')).toEqual([{ method: 'POST', path: '/v1/alerts/alert-1/fix', body: undefined }]);
  expect(calls.some(c => c.path === '/v1/actions/request-1')).toBe(true);
  await user.click(screen.getByRole('button', { name: /^Approve Restart/i }));
  await waitFor(() => expect(sign).toHaveBeenCalledOnce());
  expect(await screen.findByText('Running')).toBeVisible();
  expect(within(fixRegion).queryByText('Done')).toBeNull();
  expect((await axe.run(fixRegion, { rules: { 'color-contrast': { enabled: false } } })).violations).toEqual([]);
  expect(calls.filter(c => c.path.endsWith('/approve'))[0]?.body).toEqual({ plan_sha256: 'plan-a', webauthn: { id: 'signed-test-assertion' } });
});

it('previews each field locally, saves only on click, and shares only the typed text, version and failing check names', async () => {
  const { calls } = mount();
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const create = vi.fn<(blob: Blob) => string>().mockReturnValue('blob:report');
  Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('What happened?'), 'The app froze.');
  expect(calls.some(c => c.path.endsWith('/diagnostics'))).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Preview report' }));
  const save = await screen.findByRole('button', { name: 'Save report' });
  for (const key of Object.keys(bundle)) expect(screen.getByText(key, { selector: 'summary' })).toBeVisible();
  const url = new URL(screen.getByRole('link', { name: 'Open a public issue' }).getAttribute('href')!);
  expect(url.origin + url.pathname).toBe('https://github.com/onemindos/ONEMINDOS/issues/new');
  const body = url.searchParams.get('body')!;
  for (const value of ['The app froze.', '0.1.0', 'storage']) expect(body).toContain(value);
  for (const value of [...privateValues, 'mesh', 'future_field']) expect(body).not.toContain(value);
  expect(create).not.toHaveBeenCalled();
  expect(click).not.toHaveBeenCalled();
  await user.click(save);
  expect(click).toHaveBeenCalledOnce();
  expect((click.mock.contexts[0] as HTMLAnchorElement).download).toMatch(/^onemind-report-\d{4}-\d{2}-\d{2}\.json$/);
  const fileReader = new FileReader();
  const report = new Promise<string>(resolve => { fileReader.onload = () => resolve(String(fileReader.result)); });
  fileReader.readAsText(create.mock.calls[0]![0]);
  expect(JSON.parse(await report)).toEqual({ text: 'The app froze.', bundle });
  const reportCard = screen.getByRole('heading', { name: 'Report a problem' }).closest('section')!;
  expect(within(reportCard).getByText('The app froze.')).toBeVisible();
  expect((await axe.run(reportCard, { rules: { 'color-contrast': { enabled: false } } })).violations).toEqual([]);
});

it('omits a diagnostic gateway version that contains an address', async () => {
  mount('owner-demo', privateValues[3]);
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('What happened?'), 'Unresponsive');
  await user.click(screen.getByRole('button', { name: 'Preview report' }));
  expect(decodeURIComponent((await screen.findByRole('link', { name: 'Open a public issue' })).getAttribute('href')!)).not.toContain(privateValues[3]);
});

it.each(['adult-demo', 'guest-demo'])('gives %s owner guidance on a direct link without reading diagnostics or controls', async token => {
  const { calls } = mount(token);
  expect(await screen.findByText(token === 'guest-demo' ? /Ask an owner/ : /Ask the owner/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Download diagnostics' })).toBeNull();
  expect(screen.queryByRole('button', { name: /^Fix / })).toBeNull();
  expect(calls.some(c => c.path.startsWith('/v1/system/'))).toBe(false);
});

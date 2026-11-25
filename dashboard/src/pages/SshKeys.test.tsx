// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const FP = 'SHA256:Sm3mEwGWtcN5uE/w5uJvL4hEW37jBLnA2WL/97w+ods';
const ID = 'Sm3mEwGWtcN5uE_w5uJvL4hEW37jBLnA2WL_97w-ods';
const service = { available: true, message: null, state: 'on', port: 22, user: 'admin', reach: ['lan', 'mesh'], rate_limit: '6 new connections a minute per address', max_keys: 20 };
const key = { id: ID, fingerprint: FP, type: 'ed25519', bits: 256, comment: 'alex@laptop' };
const PUB = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGexample alex@laptop';
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }
const filed = (type: string) => response({ id: 'act-1', type, state: 'awaiting_approval' }, 202);

function mount(route: (method: string, path: string, body: unknown, headers: Headers) => Response | undefined, token = 'owner-demo', mock = false) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    return route(init?.method ?? 'GET', path, init?.body ? JSON.parse(String(init.body)) : undefined, new Headers(init?.headers)) ?? response({ error: 'not_found', message: 'no' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/account']}><SessionProvider deps={{ mock, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={mock} /></SessionProvider></MemoryRouter>);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it('lists the keys with their fingerprints and the rules SSH runs under', async () => {
  mount((method, path) => (path === '/v1/ssh' && method === 'GET' ? response({ service, keys: [key] }) : undefined));
  expect(await screen.findByText(FP)).toBeInTheDocument();
  expect(screen.getByText('alex@laptop')).toBeInTheDocument();
  expect(screen.getByText(/SSH: On, and listening/)).toBeInTheDocument();
  expect(screen.getByText(/public key only \(no password\)/)).toBeInTheDocument();
  expect(screen.queryByText(/This is a cloud box/)).not.toBeInTheDocument();
});

it('says so on a cloud box, where SSH also answers from the internet', async () => {
  mount((method, path) => (path === '/v1/ssh' && method === 'GET' ? response({ service: { ...service, reach: ['lan', 'mesh', 'internet'] }, keys: [key] }) : undefined));
  expect(await screen.findByText(/This is a cloud box: SSH also answers from the internet/)).toBeInTheDocument();
});

it('asks to add a key: it files a request and says nothing changes until an owner approves', async () => {
  const sent: unknown[] = [];
  mount((method, path, body) => {
    if (path === '/v1/ssh/keys' && method === 'POST') { sent.push(body); return filed('ssh.key.add'); }
    return path === '/v1/ssh' ? response({ service, keys: [] }) : undefined;
  });
  const user = userEvent.setup();
  expect(await screen.findByText(/No SSH keys yet/)).toBeInTheDocument();
  const ask = screen.getByRole('button', { name: 'Ask to add this key' });
  expect(ask).toBeDisabled();
  await user.type(screen.getByLabelText(/Public key/), PUB);
  await user.type(screen.getByLabelText('Name (optional)'), 'Work laptop');
  await user.click(ask);
  expect(await screen.findByText(/Nothing changes until an owner approves it/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open request in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-1');
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({ public_key: PUB, label: 'Work laptop' });
  expect(typeof (sent[0] as { idempotency_key: unknown }).idempotency_key).toBe('string');
});

it('removes a key only after a second click, by its route id', async () => {
  const calls: string[] = [];
  const keys: (string | null)[] = [];
  mount((method, path, _body, headers) => {
    if (method === 'DELETE') { calls.push(path); keys.push(headers.get('Idempotency-Key')); return filed('ssh.key.remove'); }
    return path === '/v1/ssh' ? response({ service, keys: [key] }) : undefined;
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Remove alex@laptop' }));
  expect(calls).toEqual([]);
  await user.click(screen.getByRole('button', { name: 'Confirm remove alex@laptop' }));
  await waitFor(() => expect(calls).toEqual([`/v1/ssh/keys/${ID}`]));
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/); // a retried click files one removal, not two
  expect(await screen.findByText(/Asked to remove the key/)).toBeInTheDocument();
});

it('asks to switch SSH off, and on again when it is off', async () => {
  const sent: unknown[] = [];
  let state = 'on';
  mount((method, path, body) => {
    if (path === '/v1/ssh' && method === 'PUT') { sent.push(body); state = (body as { enabled: boolean }).enabled ? 'on' : 'off'; return filed('ssh.toggle'); } // the owner approved meanwhile
    return path === '/v1/ssh' ? response({ service: { ...service, state }, keys: [key] }) : undefined;
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Ask to switch SSH off' }));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({ enabled: false });
  await user.click(await screen.findByRole('button', { name: 'Ask to switch SSH on' }));
  await waitFor(() => expect(sent).toHaveLength(2));
  expect(sent[1]).toMatchObject({ enabled: true });
});

it('shows the hub refusal for a bad key instead of failing silently', async () => {
  mount((method, path) => {
    if (path === '/v1/ssh/keys' && method === 'POST') return response({ error: 'conflict', message: 'That RSA key is only 1024 bits', reason: 'weak_key' }, 422);
    return path === '/v1/ssh' ? response({ service, keys: [] }) : undefined;
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/Public key/), 'ssh-rsa AAAA old');
  await user.click(screen.getByRole('button', { name: 'Ask to add this key' }));
  expect(await screen.findByText(/Could not ask to add the key: .*1024 bits/)).toBeInTheDocument();
});

it('says so when this box cannot manage SSH, and offers nothing to press', async () => {
  mount((_m, path) => (path === '/v1/ssh' ? response({ service: { ...service, available: false, state: 'unavailable', message: 'This box cannot manage SSH yet: the host service is not reachable.' }, keys: [] }) : undefined));
  expect(await screen.findByText(/SSH is not available on this box: This box cannot manage SSH yet/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Ask to add this key' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Ask to switch SSH/ })).not.toBeInTheDocument();
});

it('is not offered to anyone but an owner, and asks the hub nothing', async () => {
  const fetch = mount(() => undefined, 'adult-demo');
  await screen.findByRole('heading', { level: 1 });
  expect(screen.queryByText('SSH keys')).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => String(u).includes('/v1/ssh'))).toBe(false);
});

it('says demo mode has none instead of showing made-up keys', async () => {
  mount(() => undefined, 'owner-demo', true);
  expect(await screen.findByText(/Connect to a real hub to manage SSH keys/)).toHaveAttribute('role', 'status');
});

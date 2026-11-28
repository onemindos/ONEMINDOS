// SPDX-License-Identifier: Apache-2.0
// Settings > About > Rename this box (P-05) through the real HTTP client: it files PUT /v1/instance/name and
// says an owner has to approve; a bad name never reaches the hub; only an owner sees the card.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const action = (key: string) => ({ id: 'act_rename', type: 'instance.rename', state: 'awaiting_approval', params: { name: 'kitchen' }, idempotency_key: key, expires_at: '2099-01-01T00:00:00Z' });

function setup(role: 'owner' | 'adult', answer?: (init: RequestInit) => Response) {
  const calls: Array<{ path: string; init: RequestInit }> = [];
  const http = new HttpApi({
    token: 'test-only',
    fetchFn: vi.fn(async (path: string, init?: RequestInit) => {
      const p = new URL(path, window.location.origin).pathname;
      calls.push({ path: p, init: init ?? {} });
      return p === '/v1/instance/name' && init?.method === 'PUT' && answer ? answer(init) : Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
    }),
  });
  const api = Object.assign(new MockApi('owner-demo'), { renameInstance: http.renameInstance.bind(http) });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/settings/about']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-p', kind: 'person', role }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}

describe('Rename this box', () => {
  it('files the rename as a request and points the owner to Approvals', async () => {
    const u = userEvent.setup();
    const calls = setup('owner', (init) => Response.json(action(JSON.parse(String(init.body)).idempotency_key), { status: 202 }));
    await u.type(await screen.findByLabelText('Box name'), 'kitchen');
    expect(screen.getByText('kitchen.local')).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Request rename' }));
    expect(await screen.findByText(/was requested/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Approve it in Approvals/ })).toHaveAttribute('href', '/approvals');
    const put = calls.find((c) => c.init.method === 'PUT')!;
    expect(put.path).toBe('/v1/instance/name');
    expect(JSON.parse(String(put.init.body))).toMatchObject({ name: 'kitchen' });
  });

  it('refuses a name that is not one DNS label before asking the hub', async () => {
    const u = userEvent.setup();
    const calls = setup('owner', () => Response.json({}, { status: 500 }));
    await u.type(await screen.findByLabelText('Box name'), 'My Box');
    expect(screen.getByRole('alert')).toHaveTextContent(/lower-case/);
    expect(screen.getByRole('button', { name: 'Request rename' })).toBeDisabled();
    await waitFor(() => expect(calls.some((c) => c.init.method === 'PUT')).toBe(false));
  });

  it('shows the hub refusal and files nothing in the page', async () => {
    const u = userEvent.setup();
    setup('owner', () => Response.json({ error: 'conflict', message: 'finish the first-run setup before renaming the box', reason: 'setup_needed' }, { status: 409 }));
    await u.type(await screen.findByLabelText('Box name'), 'kitchen');
    await u.click(screen.getByRole('button', { name: 'Request rename' }));
    expect(await screen.findByText(/finish the first-run setup/)).toBeInTheDocument();
    expect(screen.queryByText(/was requested/)).toBeNull();
  });

  it('is not offered to someone who is not an owner', async () => {
    setup('adult');
    await screen.findByText('About');
    expect(screen.queryByLabelText('Box name')).toBeNull();
  });
});

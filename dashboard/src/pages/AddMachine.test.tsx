// SPDX-License-Identifier: Apache-2.0
// Add a machine through the real HTTP client: the ticket is one POST, the QR carries the gateway's
// payload, the join request goes to Approvals, and the box CA is a plain download link.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const CA = 'ab'.repeat(32);
const mesh = { mode: 'lan', box: 'testbox', control: { state: 'up', checked_at: null }, relay: null,
  nodes: [{ node_id: 'hub-1', name: 'testbox', role: 'hub', online: true, state: 'up', path: 'none' }], devices: [],
  names: { lan: ['testbox.local'], mesh: [] }, apps: [], https: true, ca_sha256: CA };
const join = (extra = {}) => ({ join_request_id: 'jr1', node_id: 'n2', hostname: 'r530-worker', role: 'worker', state: 'awaiting_approval', match_code: 'K7Q-2MX', action_id: 'act-9', created_at: '2026-11-21T00:00:00Z', ...extra });

function setup(opts: { joining?: unknown[]; role?: 'owner' | 'adult'; ticketFails?: boolean } = {}) {
  const tickets: unknown[] = [];
  const fetchFn = vi.fn(async (path: string, init?: RequestInit) => {
    const p = new URL(path, window.location.origin).pathname;
    if (p === '/v1/mesh') return Response.json(mesh);
    if (p === '/v1/fabric') return Response.json({ hub_node_id: 'hub-1', counts: {}, nodes: [], joining: opts.joining ?? [] });
    if (p === '/v1/tls') return Response.json({ ca_sha256: CA, names: ['testbox.local'], not_after: null, https: true, acme: null });
    if (p === '/v1/fabric/join-tickets' && init?.method === 'POST') {
      tickets.push(JSON.parse(init.body as string));
      if (opts.ticketFails) return Response.json({ error: 'permission_denied', message: 'owners only' }, { status: 403 });
      return Response.json({ ticket_id: 'tkt_1', role: 'worker', labels: {}, expires_at: new Date(Date.now() + 600_000).toISOString(), hub_ca_sha256: CA, hub_url: 'https://testbox.local',
        qr_payload: `onemind-join:v1?code=ABCD-EFGH-JKLM&ca=${CA}&role=worker&hub=x`, one_time: { join_code: 'ABCD-EFGH-JKLM' } }, { status: 201 });
    }
    return Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), {
    meshView: http.meshView.bind(http), fabricSummary: http.fabricSummary.bind(http), tlsInfo: http.tlsInfo.bind(http),
    createJoinTicket: http.createJoinTicket.bind(http), caCertUrl: http.caCertUrl.bind(http),
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/add-machine']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'p1', kind: 'person', role: opts.role ?? 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { tickets, user: userEvent.setup() };
}

describe('Add a machine', () => {
  it('shows the box certificate fingerprint with download links to the CA route', async () => {
    setup();
    expect(await screen.findByText(CA, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Download certificate/ })).toHaveAttribute('href', '/v1/tls/ca.crt?format=der');
    expect(screen.getByRole('link', { name: /PEM/ })).toHaveAttribute('href', '/v1/tls/ca.crt?format=pem');
  });

  it('makes a ticket with one POST and shows the code and QR once', async () => {
    const { tickets, user } = setup();
    await user.click(await screen.findByRole('button', { name: /Add a device/ }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /runs apps/ }));
    expect(await within(dialog).findByText('ABCD-EFGH-JKLM')).toBeInTheDocument();
    expect(within(dialog).getByRole('img', { name: /Join code ABCD-EFGH-JKLM/ })).toBeInTheDocument();
    expect(tickets).toEqual([{ role: 'worker' }]);
    await user.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByText('ABCD-EFGH-JKLM')).not.toBeInTheDocument());
  });

  it('says why when the hub refuses to make a code', async () => {
    const { user } = setup({ ticketFails: true });
    await user.click(await screen.findByRole('button', { name: /Add a device/ }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /runs apps/ }));
    expect(await screen.findByText(/owners only/)).toBeInTheDocument();
  });

  it('sends a waiting join request to its approval card instead of approving it', async () => {
    setup({ joining: [join()] });
    expect(await screen.findByText(/K7Q-2MX/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Approve$/ })).not.toBeInTheDocument();
  });

  it('does not offer a join code to someone who is not an owner', async () => {
    const { user } = setup({ role: 'adult' });
    expect(await screen.findByText(/Only an owner can make a join code/)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: /Add a device/ }));
    expect(screen.queryByRole('dialog', { name: 'Add a device' })).not.toBeInTheDocument();
  });
});

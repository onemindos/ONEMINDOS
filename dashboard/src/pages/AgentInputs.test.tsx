// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { AgentInputs } from './AgentInputs';
import { FabricPolicy } from './FabricPolicy';

const session = vi.hoisted(() => ({ signIn: vi.fn(), signOut: vi.fn() }));
vi.mock('../session', () => ({
  useSession: () => session,
  useSignedIn: () => ({ token: 'owner-token', signIn: session.signIn, principal: { id: 'owner', role: 'owner' } }),
}));
afterEach(() => vi.unstubAllGlobals());

it('loads an agent’s declaration and requests approval to reduce its outside inputs', async () => {
  const writes: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer owner-token');
    if (path === '/v1/agents') return Response.json([{ id: 'notes' }]);
    expect(path).toBe('/v1/agents/notes/inputs');
    if (init.method === 'PUT') {
      writes.push(JSON.parse(String(init.body)));
      return Response.json({ id: 'act_inputs', requested_by: { id: 'owner' }, state: 'awaiting_approval' }, { status: 202 });
    }
    return Response.json({ id: 'notes', declared: true, external_inputs: ['web', 'files'], accept_injection_risk: [] });
  }));
  render(<MemoryRouter><AgentInputs /></MemoryRouter>);
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('Agent'), 'notes');
  await user.click(await screen.findByRole('button', { name: 'Edit inputs' }));
  expect(screen.getByLabelText('Web pages')).toBeChecked();
  await user.click(screen.getByLabelText('Web pages'));
  await user.click(screen.getByRole('button', { name: 'Save inputs' }));
  expect(await screen.findByRole('link', { name: 'Review in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_inputs');
  expect(screen.getByText('Reads outside text: web, files.')).toBeVisible();
  expect(writes).toEqual([{ external_inputs: ['files'], accept_injection_risk: [] }]);
});

it('shows policy delivery lag and failure reported by the gateway', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    expect(new URL(url).pathname).toBe('/v1/fabric/policy');
    expect(init.method).toBe('GET');
    return Response.json({ epoch: 4, stop: { agents: true, motion_lockout: false }, published: { machine: 3 }, error: 'NATS unreachable' });
  }));
  render(<FabricPolicy />);
  expect(await screen.findByRole('alert')).toHaveTextContent('NATS unreachable');
  expect(screen.getByText(/Policy version 4. Agent stop on./)).toBeVisible();
  expect(screen.getByRole('list', { name: 'Published machine policies' })).toHaveTextContent('machine: version 3');
});

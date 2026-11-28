// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AgentInputsEditor, AppSharingEditor, people } from './PermissionEditors';

const session = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('../session', () => ({ useSignedIn: () => ({ token: 'fixture', mock: false, principal: { id: 'zeus', kind: 'person', role: 'owner' }, signOut: session.signOut }), useSession: () => ({ signOut: session.signOut }) }));
const webauthn = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../lib/webauthn', () => ({ getPasskey: webauthn.get }));
const box = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock('../lib/boxcode', () => ({ askBoxCode: box.ask }));
beforeEach(() => { webauthn.get.mockResolvedValue({ id: 'bio' }); box.ask.mockResolvedValue('482913'); });
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

type Call = { method: string; path: string; body: unknown; headers: Record<string, string> };
function gateway(route: (c: Call) => unknown) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const c = { method: init.method ?? 'GET', path: decodeURIComponent(new URL(url).pathname), body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers ?? {}) as Record<string, string> };
    calls.push(c);
    const out = route(c);
    if (out instanceof Response) return out;
    return out === undefined ? Response.json({ error: 'not_found', message: 'no' }, { status: 404 }) : Response.json(out);
  }));
  return calls;
}
const stepUp = (op: string, target: string, body: unknown, box?: string) => Response.json({ error: 'unauthenticated', message: 'confirm it is you', reason: 'step_up_required',
  details: [{ step_up: { op, target, body, required_level: 'L2', ...(box ? { box } : {}) } }] }, { status: 401 });
const users = [
  { id: 'usr_zeus', display_name: 'Zeus', role: 'owner' }, { id: 'usr_ada', display_name: 'Ada', role: 'adult' },
  { id: 'usr_gus', display_name: 'Gus', role: 'guest' }, { id: 'usr_kim', display_name: 'Kim', role: 'child' },
  { id: 'usr_old', display_name: 'Old', role: 'guest', disabled: true },
];
const access = { app_id: 'notes', roles: ['owner', 'adult'], people: [], auth: 'onemind' };

it('shares an app with a person, confirming with the proven key the hub names (step-up in place)', async () => {
  let shared = false;
  const calls = gateway(({ method, path, headers, body }) => {
    if (path === '/v1/apps/notes/access' && method === 'PUT') {
      if (headers['OneMind-Step-Up'] !== 'grant-1') return stepUp('apps.access.set', 'notes', body);
      shared = true; return { ...access, people: [{ id: 'usr_gus', display_name: 'Gus' }] };
    }
    if (path === '/v1/apps/notes/access') return shared ? { ...access, people: [{ id: 'usr_gus', display_name: 'Gus' }] } : access;
    if (path === '/v1/users') return users;
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-26T12:00:00Z', required_level: 'L2', grace: false, publicKey: { challenge: 'y' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-1', expires_at: '2026-11-26T12:02:00Z', level: 'L2' };
    return undefined;
  });
  render(<AppSharingEditor appId="notes" appName="Notes" />);
  const user = userEvent.setup();
  // Owners and adults always open every app, and a disabled account is not offered.
  expect(await screen.findByLabelText('Gus')).not.toBeChecked();
  expect(screen.queryByLabelText('Ada')).toBeNull();
  expect(screen.queryByLabelText('Old')).toBeNull();
  expect(screen.getByRole('button', { name: 'Save sharing' })).toBeDisabled();
  await user.click(screen.getByLabelText('Gus'));
  await user.click(screen.getByRole('button', { name: 'Save sharing' }));
  expect(await screen.findByText('Saved.')).toBeVisible();
  expect(calls.find((c) => c.path === '/v1/auth/step-up/options')?.body).toEqual({ op: 'apps.access.set', target: 'notes', body: { roles: ['owner', 'adult'], people: ['usr_gus'], auth: 'onemind' } });
  expect(webauthn.get).toHaveBeenCalledWith({ challenge: 'y' });
  expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(2);
});

it('asks for the code on the box\'s screen before the first proven key', async () => {
  const calls = gateway(({ method, path, headers, body }) => {
    if (path === '/v1/apps/notes/access' && method === 'PUT') return headers['OneMind-Step-Up'] === 'grant-b' ? access : stepUp('apps.access.set', 'notes', body, 'required');
    if (path === '/v1/apps/notes/access') return access;
    if (path === '/v1/users') return users;
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-26T12:00:00Z', required_level: 'L1', grace: true, box_code_required: true, publicKey: { challenge: 'b' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-b', expires_at: '2026-11-26T12:02:00Z', level: 'L1' };
    return undefined;
  });
  render(<AppSharingEditor appId="notes" appName="Notes" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Guests'));
  await user.click(screen.getByRole('button', { name: 'Save sharing' }));
  expect(await screen.findByText('Saved.')).toBeVisible();
  expect(box.ask).toHaveBeenCalledWith('apps.access.set');
  expect(calls.find((c) => c.path === '/v1/auth/step-up')?.body).toEqual({ credential: { id: 'bio' }, box_code: '482913' });
});

it('says plainly when the confirmation was cancelled, and nothing changed', async () => {
  webauthn.get.mockRejectedValue(Object.assign(new Error('cancelled'), { name: 'NotAllowedError' }));
  gateway(({ method, path, body }) => {
    if (path === '/v1/apps/notes/access' && method === 'PUT') return stepUp('apps.access.set', 'notes', body);
    if (path === '/v1/apps/notes/access') return access;
    if (path === '/v1/users') return users;
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-26T12:00:00Z', required_level: 'L2', grace: false, publicKey: { challenge: 'y' } };
    return undefined;
  });
  render(<AppSharingEditor appId="notes" appName="Notes" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Kim'));
  await user.click(screen.getByRole('button', { name: 'Save sharing' }));
  expect(await screen.findByText(/Sharing was not changed: the passkey check was cancelled or timed out/)).toBeVisible();
});

it('declares what an agent reads; an undeclared agent starts with everything ticked (fail closed)', async () => {
  const calls = gateway(({ method, path, body }) => {
    if (path === '/v1/agents/agent:hermes/inputs' && method === 'PUT') return { id: 'agent:hermes', ...(body as object), declared: true, exposed: true, permanently_tainted: true, accept_injection_risk_effective: false };
    if (path === '/v1/agents/agent:hermes/inputs') return { id: 'agent:hermes', external_inputs: ['undeclared'], declared: false, exposed: true, permanently_tainted: true, accept_injection_risk: [], accept_injection_risk_effective: false };
    return undefined;
  });
  render(<AgentInputsEditor agentId="agent:hermes" />);
  const user = userEvent.setup();
  expect(await screen.findByText(/You haven’t said what this agent reads yet/)).toBeVisible();
  for (const name of ['Web pages', 'Email', 'Files it opens itself', 'Many chats on one token (a chat host)']) expect(screen.getByLabelText(name)).toBeChecked();
  await user.click(screen.getByLabelText('Email'));
  await user.click(screen.getByLabelText('Many chats on one token (a chat host)'));
  await user.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ external_inputs: ['web', 'files'], accept_injection_risk: [] }));
});

it('loosening an agent to read nothing goes through the step-up the hub names', async () => {
  let declared = { id: 'agent:hermes', external_inputs: ['web'], declared: true, exposed: true, permanently_tainted: true, accept_injection_risk: [], accept_injection_risk_effective: false };
  const calls = gateway(({ method, path, headers, body }) => {
    if (path === '/v1/agents/agent:hermes/inputs' && method === 'PUT') {
      if (headers['OneMind-Step-Up'] !== 'grant-a') return stepUp('agents.inputs.set', 'agent:hermes', body);
      declared = { ...declared, external_inputs: [], exposed: false, permanently_tainted: false }; return declared;
    }
    if (path === '/v1/agents/agent:hermes/inputs') return declared;
    if (path === '/v1/auth/step-up/options') return { challenge_id: 's', expires_at: '2026-11-26T12:00:00Z', required_level: 'L2', grace: false, publicKey: { challenge: 'a' } };
    if (path === '/v1/auth/step-up') return { step_up: 'grant-a', expires_at: '2026-11-26T12:02:00Z', level: 'L2' };
    return undefined;
  });
  render(<AgentInputsEditor agentId="agent:hermes" />);
  const user = userEvent.setup();
  expect(await screen.findByText(/it reads outside text, so you approve each of its requests/)).toBeVisible();
  await user.click(screen.getByLabelText('Web pages'));
  expect(screen.getByText(/Nothing ticked: you are saying it reads nothing outside OneMind/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText(/it reads nothing outside OneMind that the gateway cannot see/)).toBeVisible();
  expect(calls.find((c) => c.path === '/v1/auth/step-up/options')?.body).toEqual({ op: 'agents.inputs.set', target: 'agent:hermes', body: { external_inputs: [], accept_injection_risk: [] } });
});

it('reads the people on the box through the generated type, leaving disabled accounts out', () => {
  const u = (id: string, display_name: string, role: string, disabled = false) => ({ id, username: null, display_name, role, disabled, enrolled: true, passkeys: 0, totp: false });
  expect(people([u('usr_gus', 'Gus', 'guest'), u('usr_old', 'Old', 'guest', true), u('usr_x', '', 'child')])).toEqual([
    { id: 'usr_gus', name: 'Gus', role: 'guest' }, { id: 'usr_x', name: 'usr_x', role: 'child' },
  ]);
});

it('signs out when the sign-in lapsed while saving, and shows no note', async () => {
  gateway(({ method, path }) => {
    if (path === '/v1/apps/notes/access' && method === 'PUT') return Response.json({ error: 'unauthenticated', message: 'unknown token' }, { status: 401 });
    if (path === '/v1/apps/notes/access') return access;
    if (path === '/v1/users') return users;
    return undefined;
  });
  render(<AppSharingEditor appId="notes" appName="Notes" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Guests'));
  await user.click(screen.getByRole('button', { name: 'Save sharing' }));
  await waitFor(() => expect(session.signOut).toHaveBeenCalled());
  expect(screen.queryByText(/Sharing was not changed/)).toBeNull();
});

it('a 401 that names a step-up reason is explained, not a sign-out', async () => {
  gateway(({ method, path }) => {
    if (path === '/v1/agents/agent:hermes/inputs' && method === 'PUT') return Response.json({ error: 'unauthenticated', message: 'too many', reason: 'box_code_locked' }, { status: 401 });
    if (path === '/v1/agents/agent:hermes/inputs') return { id: 'agent:hermes', external_inputs: ['web'], declared: true, exposed: true, permanently_tainted: true, accept_injection_risk: [], accept_injection_risk_effective: false };
    return undefined;
  });
  render(<AgentInputsEditor agentId="agent:hermes" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Email'));
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText(/too many wrong codes from the box's screen/)).toBeVisible();
  expect(session.signOut).not.toHaveBeenCalled();
});

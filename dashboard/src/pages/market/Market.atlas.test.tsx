// SPDX-License-Identifier: Apache-2.0
// Atlas Market (04) and the app page's waiting track (05): the sidebar counts come from the hub,
// Bring your own is on Discover for owners only, Requests lists app requests, and the waiting track
// approves and cancels through the same gateway calls Approvals uses (D-027).
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { MockApi } from '../../api/mock';
import { ApiError, type Action, type ApproveBody, type Principal } from '../../api/types';
import { SessionProvider } from '../../session';
import { askedBy, isAppRequest, ownsRequest, sortRequests } from './requests';
import { waitingSteps } from './AppWaitingTrack';

vi.mock('../../lib/webauthn', async (orig) => ({
  ...(await orig<typeof import('../../lib/webauthn')>()),
  webauthnSupported: () => true,
  getPasskey: vi.fn(async () => ({ id: 'cred-1', type: 'public-key' })),
}));

const T = { timeout: 4000 };
const SHA = 'sha256:plan-one';
const future = () => new Date(Date.now() + 3600_000).toISOString();
const OWNER: Principal = { id: 'owner', kind: 'person', role: 'owner' };

function waitingAction(over: Partial<Action> = {}): Action {
  return {
    id: 'act-wait', type: 'app.install', params: { app_id: 'ollama' }, idempotency_key: 'k', expires_at: future(), state: 'awaiting_approval',
    plan: { summary: 'Install Uptime Kuma.', objects: [], images: [], volumes: [], nodes: [], warnings: [], network_paths: [] } as unknown as Action['plan'],
    plan_sha256: SHA, requested_by: OWNER, created_at: new Date(Date.now() - 120_000).toISOString(), ...over,
  };
}

function setup(route: string, opts: { actions?: Action[]; token?: string; principal?: Principal; secrets?: boolean; licence?: boolean; noPrincipal?: boolean } = {}) {
  const approved: Array<{ id: string; body?: ApproveBody }> = [];
  const denied: string[] = [];
  const token = opts.token ?? 'owner-demo';
  const api = new MockApi(token);
  let list = opts.actions ?? [];
  Object.assign(api, {
    actions: async () => list,
    action: async (id: string) => list.find((a) => a.id === id)!,
    me: async () => ({ principal: opts.principal ?? OWNER, token: null, session: null, passkeys: 1, scopes: opts.noPrincipal ? ['*'] : [], capabilities: [], step_up: { passkeys_active: true, require_passkey_approval: false } }),
    approveOptions: async () => ({ challenge: 'c', action_sha256: 'a', plan_sha256: SHA, expires_at: future(), publicKey: { challenge: 'c' } }),
    approve: async (id: string, body?: ApproveBody) => {
      if (opts.licence) throw new ApiError(409, 'stale_precondition', 'licence not accepted', 'licence_unconfirmed');
      approved.push({ id, body });
      list = list.map((a) => (a.id === id ? { ...a, state: 'accepted' as const } : a));
      return list.find((a) => a.id === id)!;
    },
    deny: async (id: string) => {
      denied.push(id);
      list = list.map((a) => (a.id === id ? { ...a, state: 'cancelled' as const } : a));
      return list.find((a) => a.id === id)!;
    },
    appSecrets: async () => ({ app_id: 'ollama', key_id: 'k1', missing_required: [], secrets: opts.secrets ? [{ name: 'auth', description: 'Auth', keys: [{ key: 'API_KEY', kind: 'api-key', description: 'Key', required: true, source: 'owner', set: false, version: null, updated_at: null }] }] : [] }),
    sources: async () => [{ id: 'src_1', name: 'Rivera family list', url: 'https://git.example.org/apps', commit: 'b'.repeat(40), state: 'ready', apps: [{ id: 'whoami' }, { id: 'other' }], errors: [] }],
  });
  window.sessionStorage.setItem('onemind.token', token);
  render(
    <MemoryRouter initialEntries={[route]}>
      <SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => (opts.noPrincipal ? undefined : opts.principal ?? OWNER) }}>
        <App mock={false} />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { approved, denied, user: userEvent.setup() };
}

describe('requests helpers', () => {
  it('counts only app actions that name an app, waiting first', () => {
    const a = waitingAction();
    const done = waitingAction({ id: 'old', state: 'succeeded', created_at: new Date().toISOString() });
    const machine = { ...waitingAction({ id: 'm' }), type: 'machine.delete', params: { name: 'vm' } } as unknown as Action;
    expect(isAppRequest(a)).toBe(true);
    expect(isAppRequest(machine)).toBe(false);
    expect(sortRequests([done, a]).map((x) => x.id)).toEqual(['act-wait', 'old']);
  });

  it('says "you" only for the person who asked; an agent is labelled as one', () => {
    expect(ownsRequest(waitingAction(), OWNER)).toBe(true);
    expect(askedBy(waitingAction({ requested_by: { id: 'ops-agent', kind: 'agent', role: 'agent' } }), OWNER)).toBe('ops-agent (agent)');
    expect(askedBy(waitingAction({ requested_by: undefined }), OWNER)).toBe('not reported');
  });

  it('a request with no plan from the hub is never shown as checked', () => {
    const steps = waitingSteps(waitingAction({ plan: null, plan_sha256: undefined }), { scan: null }, Date.now(), OWNER, true);
    expect(steps.map((s) => s.title)).toEqual(['Requested', 'Plan checked', 'Your approval', 'Install', 'Running']);
    expect(steps[1]).toMatchObject({ state: 'problem', detail: 'The hub sent no plan' });
    expect(waitingSteps(waitingAction(), { scan: { result: 'pass', scanned_at: new Date().toISOString() } as never }, Date.now(), OWNER, true)[1]!.state).toBe('done');
  });
});

describe('Atlas Market', () => {
  it('Discover has the sidebar with hub counts, sources from the hub and Bring your own with real commands', async () => {
    setup('/market', { actions: [waitingAction()] });
    const nav = await screen.findByRole('navigation', { name: 'Market' }, T);
    await waitFor(() => expect(within(nav).getByRole('link', { name: /Requests\s*1/ })).toBeInTheDocument(), T);
    expect(await within(nav).findByText('Rivera family list', {}, T)).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Git repository' })).toHaveAttribute('href', '/custom');
    const byo = screen.getByRole('region', { name: /Bring your own/ });
    expect(within(byo).getByText('$ onemind app deploy --git URL --ref REF')).toBeInTheDocument();
    expect(within(byo).getByText('$ onemind plugins list')).toBeInTheDocument();
  });

  it('a person who cannot decide sees no Bring your own and no owner sources', async () => {
    setup('/market', { token: 'adult-demo', principal: { id: 'alex', kind: 'person', role: 'adult' } });
    const nav = await screen.findByRole('navigation', { name: 'Market' }, T);
    expect(within(nav).queryByText('Bring your own')).toBeNull();
    expect(within(nav).queryByText('Rivera family list')).toBeNull();
    expect(screen.queryByRole('region', { name: /Bring your own/ })).toBeNull();
  });

  it('Requests lists app requests with who asked and links waiting ones to Approvals', async () => {
    setup('/market/requests', { actions: [waitingAction(), waitingAction({ id: 'act-done', state: 'succeeded', type: 'app.remove', params: { app_id: 'jellyfin' } })] });
    const list = await screen.findByRole('list', { name: 'App requests' }, T);
    const rows = within(list).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent(/Install .*Asked by you.*Waiting for approval/);
    expect(within(rows[0]!).getByRole('link', { name: 'Review in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act-wait');
    expect(rows[1]).toHaveTextContent(/Remove .*Done/);
  });

  it('Requests says so when there are none', async () => {
    setup('/market/requests');
    expect(await screen.findByText('No app requests', {}, T)).toBeInTheDocument();
  });
});

describe('App page waiting track', () => {
  it('shows the five steps and approves with a passkey bound to the plan', async () => {
    const { approved, user } = setup('/market/ollama', { actions: [waitingAction()] });
    const track = await screen.findByRole('region', { name: /waits for your approval/ }, T);
    expect(within(track).getByRole('list', { name: 'Request progress' }).children).toHaveLength(5);
    expect(within(track).getByText('onemind actions approve act-wait')).toBeInTheDocument();
    await user.click(await within(track).findByRole('button', { name: 'Approve with passkey' }, T));
    await waitFor(() => expect(approved).toHaveLength(1), T);
    expect(approved[0]!.body).toMatchObject({ plan_sha256: SHA, webauthn: { id: 'cred-1' } });
  });

  it('the requester cancels their own request (a deny, recorded as cancelled)', async () => {
    const { denied, user } = setup('/market/ollama', { actions: [waitingAction()] });
    const track = await screen.findByRole('region', { name: /waits for your approval/ }, T);
    await user.click(within(track).getByRole('button', { name: 'Cancel request' }));
    await waitFor(() => expect(denied).toEqual(['act-wait']), T);
  });

  it('an install that needs owner-typed secrets is finished in Approvals, never approved here', async () => {
    const { approved, user } = setup('/market/ollama', { actions: [waitingAction()], secrets: true });
    const track = await screen.findByRole('region', { name: /waits for your approval/ }, T);
    await user.click(await within(track).findByRole('button', { name: 'Approve with passkey' }, T));
    await screen.findByRole('heading', { name: /Approvals/ }, T);
    expect(approved).toEqual([]);
  });

  it('a waiting request blocks a second Request install (the hub would file another action)', async () => {
    setup('/market/ollama', { actions: [waitingAction()] });
    await screen.findByRole('region', { name: /waits for your approval/ }, T);
    expect(await screen.findByRole('button', { name: /Request install/ }, T)).toBeDisabled();
    expect(screen.getByText('An install request for this app is already waiting for approval.')).toBeInTheDocument();
  });

  it('on a real box the viewer comes from GET /v1/me: Cancel request and "You" show without an injected principal', async () => {
    setup('/market/ollama', { actions: [waitingAction()], noPrincipal: true });
    const track = await screen.findByRole('region', { name: /You asked to install this/ }, T);
    expect(await within(track).findByRole('button', { name: 'Cancel request' }, T)).toBeInTheDocument();
    expect(within(track).getByText(/^You · /)).toBeInTheDocument();
  });

  it('a hold request is finished in Approvals, never approved here', async () => {
    const { approved, user } = setup('/market/ollama', { actions: [waitingAction({ approval: { hold: true, hold_ms: 2000, physical: false } as Action['approval'] })] });
    const track = await screen.findByRole('region', { name: /waits for your approval/ }, T);
    await user.click(await within(track).findByRole('button', { name: 'Approve with passkey' }, T));
    await screen.findByRole('heading', { name: /Approvals/ }, T);
    expect(approved).toEqual([]);
  });

  it('a licence the hub wants accepted sends the owner to Approvals', async () => {
    const { approved, user } = setup('/market/ollama', { actions: [waitingAction()], licence: true });
    const track = await screen.findByRole('region', { name: /waits for your approval/ }, T);
    await user.click(await within(track).findByRole('button', { name: 'Approve with passkey' }, T));
    await screen.findByRole('heading', { name: /Approvals/ }, T);
    expect(approved).toEqual([]);
  });

  it('an owner without a passkey is not told "Passkey"', () => {
    const steps = waitingSteps(waitingAction(), { scan: null }, Date.now(), OWNER, true, false);
    expect(steps[2]!.detail).not.toMatch(/Passkey/);
    expect(waitingSteps(waitingAction(), { scan: null }, Date.now(), OWNER, true, true)[2]!.detail).toMatch(/^Passkey · /);
  });

  it('a non-owner sees the track without decision buttons', async () => {
    setup('/market/ollama', { actions: [waitingAction({ requested_by: { id: 'alex', kind: 'person', role: 'adult' } })], token: 'adult-demo', principal: { id: 'alex', kind: 'person', role: 'adult' } });
    const track = await screen.findByRole('region', { name: /waits for an owner/ }, T);
    expect(within(track).queryByRole('button', { name: /Approve/ })).toBeNull();
    expect(within(track).getByRole('link', { name: 'See the request' })).toHaveAttribute('href', '/approvals?highlight=act-wait');
  });
});

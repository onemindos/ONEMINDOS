// SPDX-License-Identifier: Apache-2.0
// PLG-GIT-01: the Custom apps tab against the /v1/custom-apps routes through HttpApi. Checking a repository
// installs nothing and files no action; the install or update stays an owner's request in Approvals.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const COMMIT = 'a'.repeat(40);
const OLD = 'b'.repeat(40);
const READY = { url: 'https://git.example.org/me/notes', ref: 'main', commit: COMMIT, app_id: 'notes', name: 'Notes', version: '1.1.0', revision: 2, verdict: 'ready', problems: [], notes: ['A Containerfile is in the repository, but building images is not part of this release.'], scan: { result: 'pass', scanned_at: '2026-11-25T10:00:00Z' }, signature: { policy: 'undecided', status: 'not_checked', detail: 'No signing policy for custom apps is decided yet; this app is unsigned and capped at community.' }, action_type: 'app.install' };
const BLOCKED = { ...READY, app_id: 'notes', verdict: 'blocked', problems: ['F-01 Deployment/notes: spec.hostNetwork is not allowed'], action_type: null };
const APPS = [{ app_id: 'notes', url: READY.url, ref: 'main', status: 'installed', current_revision: 2, deployed_revision: 2, rollback_to: 1, revisions: [
  { revision: 2, commit: COMMIT, ref: 'main', version: '1.1.0', scan: { result: 'pass', scanned_at: '2026-11-25T10:00:00Z' }, created_at: '2026-11-25T10:00:00Z', deployed_at: '2026-11-25T10:05:00Z', current: true, deployed: true },
  { revision: 1, commit: OLD, ref: 'main', version: '1.0.0', scan: { result: 'pass', scanned_at: '2026-11-24T10:00:00Z' }, created_at: '2026-11-24T10:00:00Z', deployed_at: '2026-11-24T10:05:00Z', current: false, deployed: false }] }];

function setup(opts: { plan?: unknown; role?: 'owner' | 'adult' } = {}) {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, window.location.origin).pathname;
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    if (init?.method === 'POST') writes.push({ path, body });
    if (path === '/v1/custom-apps') return Response.json(APPS);
    if (path === '/v1/custom-apps/plan') return Response.json(opts.plan ?? READY);
    if (path === '/v1/custom-apps/notes/rollback') return Response.json({ app_id: 'notes', from_revision: 2, to_revision: 1, commit: OLD, version: '1.0.0', action_type: 'app.update', verdict: 'ready', next: 'Request the update' });
    return Response.json({});
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), {
    customApps: http.customApps.bind(http), planCustomApp: http.planCustomApp.bind(http), rollbackCustomApp: http.rollbackCustomApp.bind(http),
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/custom']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-user', kind: 'person', role: opts.role ?? 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { writes, user: userEvent.setup() };
}

describe('custom apps (PLG-GIT-01)', () => {
  it('checks a repository, shows the plan and the signing seam, and files no action', async () => {
    const { user, writes } = setup();
    await user.type(await screen.findByLabelText('Git URL'), READY.url);
    await user.click(screen.getByRole('button', { name: 'Check repository' }));
    const plan = await screen.findByRole('region', { name: 'Plan' });
    expect(within(plan).getByText('Notes 1.1.0')).toBeInTheDocument();
    expect(within(plan).getByText(/Signature: not checked \(undecided\)/)).toBeInTheDocument();
    expect(within(plan).getByText(/building images is not part of this release/)).toBeInTheDocument();
    expect(within(plan).getByRole('link', { name: 'Request the install' })).toHaveAttribute('href', '/market/notes');
    expect(writes).toEqual([{ path: '/v1/custom-apps/plan', body: { url: READY.url, ref: 'main' } }]);
  });

  it('shows the problems of a repository that did not pass and offers no install', async () => {
    const { user } = setup({ plan: BLOCKED });
    await user.type(await screen.findByLabelText('Git URL'), READY.url);
    await user.click(screen.getByRole('button', { name: 'Check repository' }));
    const plan = await screen.findByRole('region', { name: 'Plan' });
    expect(within(plan).getByText('Not ready')).toBeInTheDocument();
    expect(within(plan).getByText(/spec.hostNetwork is not allowed/)).toBeInTheDocument();
    expect(within(plan).queryByRole('link', { name: /Request the/ })).not.toBeInTheDocument();
    expect(within(plan).getByText('Nothing was installed.')).toBeInTheDocument();
  });

  it('lists revisions and prepares a rollback that still waits for the owner', async () => {
    const { user, writes } = setup();
    const table = await screen.findByRole('table', { name: 'Revisions of notes' });
    expect(within(table).getByText('running')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Roll back notes to revision 1' }));
    const plan = await screen.findByRole('region', { name: 'Rollback plan' });
    expect(within(plan).getByText(/from revision 2 back to revision 1/)).toBeInTheDocument();
    expect(within(plan).getByRole('link', { name: 'Request the update' })).toHaveAttribute('href', '/installed/notes');
    await waitFor(() => expect(writes).toEqual([{ path: '/v1/custom-apps/notes/rollback', body: {} }]));
  });

  it('keeps the tab away from a non-owner, as for sources, and sends nothing', async () => {
    const { writes } = setup({ role: 'adult' });
    expect(await screen.findByText(/Only an owner can use this/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check repository' })).not.toBeInTheDocument();
    expect(writes).toEqual([]);
  });
});

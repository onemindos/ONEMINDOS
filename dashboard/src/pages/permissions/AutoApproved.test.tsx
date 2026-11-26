// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { PermissionsPage } from './PermissionsPage';

vi.mock('../../session', () => ({
  useSession: () => ({ signOut: vi.fn() }),
  useSignedIn: () => ({ token: 'owner-session', signIn: vi.fn(), api: { logout: vi.fn() }, anon: {} }),
}));
vi.mock('../../shell/Shell', () => ({ useShell: () => ({ role: 'owner' }) }));
afterEach(() => vi.unstubAllGlobals());

const line = (seq: number, data: Record<string, unknown>) => ({ seq, ts: `2026-11-2${seq}T10:00:00Z`, event: 'action.approved', principal: { id: 'x' }, action_id: `act_${seq}`, data, prev_hash: '', hash: '' });

it('lists what rules approved, newest first, skips approvals a person made, and revokes a rule with one tap', async () => {
  const calls: Array<{ method: string; path: string; search: string }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const u = new URL(url);
    calls.push({ method: init.method ?? 'GET', path: u.pathname, search: u.search });
    if (u.pathname === '/v1/audit/events') return Response.json([
      line(1, { type: 'backup.run', requested_by: 'agent:helper', approved_via: 'policy', policy_id: 'pol_1', policy_revision: 2, uses: '1/10' }),
      line(2, { type: 'app.install', requested_by: 'agent:helper', approved_by: 'owner' }),
      line(3, { type: 'notes.read', requested_by: 'agent:reader', approved_via: 'policy', policy_id: 'pol_2', uses: '4/10', forever: true }),
    ]);
    return Response.json({ id: 'pol_2', state: 'revoked' });
  }));
  render(<MemoryRouter initialEntries={['/settings/permissions/auto-approved']}><Routes><Route path="/settings/:section/:tab?/:item?" element={<PermissionsPage />} /></Routes></MemoryRouter>);
  const list = await screen.findByRole('list', { name: 'Approved by your rules' });
  const items = within(list).getAllByRole('listitem');
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent('notes.read for reader');
  expect(within(items[0]!).getByText('Forever')).toBeVisible();
  expect(within(items[1]!).getByRole('link', { name: 'Rule, revision 2' })).toHaveAttribute('href', '/settings/permissions/rules/pol_1');
  expect(screen.queryByText(/app.install/)).toBeNull();
  expect(calls[0]!.search).toContain('event=action.approved');
  expect(calls[0]!.search).toContain('since=');
  await userEvent.setup().click(within(items[0]!).getByRole('button', { name: /^Revoke the rule that approved notes.read/ }));
  expect(await screen.findByRole('status')).toHaveTextContent('Rule revoked.');
  expect(calls.filter((c) => c.method === 'POST')).toEqual([expect.objectContaining({ path: '/v1/approval-policies/pol_2/revoke' })]);
});

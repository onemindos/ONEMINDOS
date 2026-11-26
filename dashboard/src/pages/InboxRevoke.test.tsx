// SPDX-License-Identifier: Apache-2.0
// Gateway permissions PR 13: an approval.auto notice carries a Revoke rule button (never Approve).
// One tap ends the rule (POST /v1/approval-policies/{id}/revoke), with no passkey: it only narrows.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { ToastProvider } from '@onemind/ui';
import { afterEach, expect, it, vi } from 'vitest';
import { Inbox } from './Inbox';

const notice = {
  id: 'n1', severity: 'info', topic: 'approvals', title: 'Approved by your rule: backup.run', body: 'agent:helper asked; rule pol_7 approved it.',
  link: '/settings/permissions/rules/pol_7', source: 'gateway', action_id: 'act_1', alert_id: null, created_at: '2026-11-26T00:00:00Z', read_at: null,
  actions: [{ id: 'revoke', label: 'Revoke rule', kind: 'revoke', policy_id: 'pol_7' }, { id: 'rule', label: 'See the rule', kind: 'open', link: '/settings/permissions/rules/pol_7' }],
};
vi.mock('../session', () => ({
  useSession: () => ({ signOut: vi.fn() }),
  useSignedIn: () => ({ token: 'owner-session', person: 'owner', mock: false,
    api: { notifications: async () => [notice], channels: async () => [], markRead: vi.fn() } }),
}));
vi.mock('../data/hub', () => ({ useHub: () => ({ now: Date.parse('2026-11-26T00:05:00Z') }) }));
afterEach(() => vi.unstubAllGlobals());

it('revokes the rule from the notice with one tap and never offers an approve button', async () => {
  const fetch = vi.fn(async () => Response.json({ id: 'pol_7', state: 'revoked' }));
  vi.stubGlobal('fetch', fetch);
  render(<MemoryRouter><ToastProvider><Inbox /></ToastProvider></MemoryRouter>);
  const button = await screen.findByRole('button', { name: 'Revoke rule: Approved by your rule: backup.run' });
  expect(screen.queryByRole('button', { name: /^approve/i })).toBeNull();
  expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/settings/permissions/rules/pol_7');
  await userEvent.setup().click(button);
  expect(await screen.findByText('Rule revoked')).toBeVisible();
  const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
  expect(new URL(url).pathname).toBe('/v1/approval-policies/pol_7/revoke');
  expect(init.method).toBe('POST');
});

// SPDX-License-Identifier: Apache-2.0
// UX-01 (#206): Simple and Pro by role. No global Pro switch: owners and adults get the Pro screens
// (Nodes, Control Hub, AI & Agents, Storage, Backups); guests and children get the simple set, and
// a direct link to a Pro screen shows a calm "not for your role" line instead of the screen.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { AuditRecord } from './api/wiring';
import { agentRecords, agentSummaries } from './data/audit';
import { roleOf, showsNav, viewFor } from './shell/roles';
import { renderApp, seriousViolations } from './test/helpers';

const T = { timeout: 4000 };
const PRO_LINKS = ['Nodes', 'Control Hub', 'AI & Agents', 'Storage', 'Backups'];

async function mainNav() {
  return within(await screen.findByRole('navigation', { name: 'Main' }, T));
}

describe('role → view', () => {
  it('owner and adult are Pro; guest, child and agent are Simple; unknown stays unknown', () => {
    expect(viewFor('owner')).toBe('pro');
    expect(viewFor('adult')).toBe('pro');
    for (const r of ['guest', 'child', 'agent', null]) expect(viewFor(r)).toBe('simple');
    expect(viewFor(undefined)).toBe('unknown');
    expect(showsNav('control-hub', 'unknown')).toBe(false);
    expect(showsNav('home', 'simple')).toBe(true);
  });

  it('reads the role from GET /v1/me when the session does not carry it', () => {
    const me = (kind: string, role: string | null) => ({ principal: { id: 'x', kind, role } }) as Parameters<typeof roleOf>[1];
    expect(roleOf(undefined, me('person', 'adult'))).toBe('adult');
    expect(roleOf(undefined, me('agent', null))).toBe('agent');
    expect(roleOf(undefined, undefined)).toBeUndefined();
  });
});

describe.each([
  ['owner-demo', true],
  ['adult-demo', true],
  ['guest-demo', false],
  ['child-demo', false],
])('navigation for %s', (token, pro) => {
  it(pro ? 'shows the Pro screens' : 'shows only the simple screens', async () => {
    renderApp({ token });
    const nav = await mainNav();
    expect(nav.getByRole('link', { name: /Home/ })).toBeInTheDocument();
    for (const name of PRO_LINKS) {
      const link = nav.queryByRole('link', { name: new RegExp(`^${name}`) });
      if (pro) expect(link).toBeInTheDocument();
      else expect(link).not.toBeInTheDocument();
    }
  });
});

describe('Pro routes for a Simple role', () => {
  it.each(['/control-hub', '/agents', '/nodes'])('a child opening %s gets the role notice, not the screen', async (route) => {
    renderApp({ token: 'child-demo', route });
    expect(await screen.findByText(/for the people who run this box/, {}, T)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});

describe('role from GET /v1/me (real gateway: the session has no role)', () => {
  it('an owner gets the Pro nav once /v1/me answers', async () => {
    renderApp({ token: 'owner-demo', knownRole: false });
    const nav = await mainNav();
    expect(await nav.findByRole('link', { name: /^Control Hub/ }, T)).toBeInTheDocument();
  });
});

describe('Control Hub', () => {
  it('lists machines and workloads from the hub and files a request, never a direct change', async () => {
    const u = userEvent.setup();
    const { container } = renderApp({ token: 'owner-demo', route: '/control-hub' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Control Hub' }, T)).toBeInTheDocument();
    const machines = await screen.findByRole('table', { name: 'Machines' }, T);
    expect(within(machines).getAllByRole('row').length).toBeGreaterThan(1);
    const workloads = await screen.findByRole('table', { name: 'Workloads' }, T);
    const restart = within(workloads).getAllByRole('button', { name: /^Request restart of/ })[0]!;
    await u.click(restart);
    expect(await screen.findByRole('dialog', { name: 'Review app request' }, T)).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('AI & Agents audit', () => {
  it('the owner sees agent records from the audit chain and a per-agent summary', async () => {
    renderApp({ token: 'owner-demo', route: '/agents' });
    // The loading timeline is replaced once the chain answers, so wait for the data first.
    expect(await screen.findByText(/action\.requested/, {}, T)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'AI & Agents' })).toBeInTheDocument();
    // The owner's sign-in is not an agent record.
    expect(screen.queryByText(/auth\.login\.succeeded/)).not.toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Agents' });
    expect(within(table).getByText('ops-agent')).toBeInTheDocument();
  });

  it('when the chain cannot be read it falls back to the agents’ requests and says so', async () => {
    renderApp({ token: 'adult-demo', route: '/agents' });
    expect(await screen.findByText('Not the audit chain', {}, T)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/ops-agent/).length).toBeGreaterThan(0), T);
  });

  it('agentRecords keeps agent records and the decisions on their actions only', () => {
    const r = (seq: number, event: string, kind: string | null, action_id: string | null, id = kind ?? 'system'): AuditRecord => ({
      seq, ts: `2026-11-18T00:00:0${seq}Z`, event, principal: kind ? { id, kind } : null, action_id, data: {}, hash: String(seq).padStart(8, '0'), prev_hash: '',
    });
    const rows = [
      r(1, 'auth.login.succeeded', 'person', null, 'owner'),
      r(2, 'action.requested', 'agent', 'a1', 'ops-agent'),
      r(3, 'action.approved', 'person', 'a1', 'owner'),
      r(4, 'action.requested', 'person', 'a2', 'owner'),
      r(5, 'action.denied', 'person', 'a2', 'owner'),
    ];
    expect(agentRecords(rows).map((x) => x.seq)).toEqual([2, 3]);
    expect(agentSummaries(rows)).toEqual([{ id: 'ops-agent', requests: 1, approved: 1, denied: 0, last: '2026-11-18T00:00:02Z' }]);
  });
});

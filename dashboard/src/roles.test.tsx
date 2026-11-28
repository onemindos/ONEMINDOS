// SPDX-License-Identifier: Apache-2.0
// UX-01 (#206): Simple and Pro by role. No global Pro switch: owners and adults get the Pro screens
// (Nodes, Control Hub, AI & Agents, Storage, Backups); guests and children get the simple set, and
// a direct link to a Pro screen shows a calm "not for your role" line instead of the screen.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildPaletteCommands } from '@onemind/ui';
import { MockWiringBase } from './api/mockWiring';
import { ApiError } from './api/types';
import type { AuditRecord } from './api/wiring';
import { agentRecords, agentSummaries } from './data/audit';
import { AGENTS_WINDOW_NOTE } from './pages/Agents';
import { abilitiesFromMe } from './session';
import { meRetryDelay, roleOf, showsNav, viewFor } from './shell/roles';
import { paletteShows } from './shell/Shell';
import { renderApp, screensNav, seriousViolations } from './test/helpers';

const T = { timeout: 4000 };
const PRO_LINKS = ['Nodes', 'Control Hub', 'AI & Agents', 'Storage', 'Backups'];

/** All screens offered to this person: Launchpad on the desktop (D-016). */
async function mainNav() {
  return screensNav(userEvent.setup(), T.timeout);
}

describe('role → view', () => {
  it('owner and adult are Pro; guest, child, teen and agent are Simple; unknown stays unknown', () => {
    expect(viewFor('owner')).toBe('pro');
    expect(viewFor('adult')).toBe('pro');
    for (const r of ['guest', 'child', 'teen', 'agent', null]) expect(viewFor(r)).toBe('simple');
    expect(viewFor(undefined)).toBe('unknown');
    expect(showsNav('control-hub', 'unknown')).toBe(false);
    expect(showsNav('home', 'simple')).toBe(true);
  });

  it('the Network screen is for owners only: an adult is Pro but gets no nav entry or palette command', () => {
    expect(showsNav('network', 'pro', 'owner')).toBe(true);
    expect(showsNav('network', 'pro', 'adult')).toBe(false);
    expect(showsNav('network', 'pro', undefined)).toBe(false);
    expect(showsNav('network', 'simple', 'owner')).toBe(false);
    expect(showsNav('storage', 'pro', 'adult')).toBe(true);
    const go = { id: 'go:network', href: '#/network' } as Parameters<typeof paletteShows>[0];
    expect(paletteShows(go, 'pro', 'owner')).toBe(true);
    expect(paletteShows(go, 'pro', 'adult')).toBe(false);
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
  ['teen-demo', false],
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
  it.each(['child-demo', 'teen-demo'].flatMap((t) => ['/control-hub', '/agents', '/nodes'].map((r) => [t, r])))('%s opening %s gets the role notice, not the screen', async (token, route) => {
    renderApp({ token, route });
    expect(await screen.findByText(/for the people who run this box/, {}, T)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});

describe('role from GET /v1/me (real gateway: the session has no role)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('an owner gets the Pro nav once /v1/me answers', async () => {
    renderApp({ token: 'owner-demo', knownRole: false });
    const nav = await mainNav();
    expect(await nav.findByRole('link', { name: /^Control Hub/ }, T)).toBeInTheDocument();
  });

  it('a failed lookup is retried, so a network hiccup does not leave the owner in Simple', async () => {
    const me = vi.spyOn(MockWiringBase.prototype, 'me').mockRejectedValueOnce(new ApiError(0, 'network', 'hub unreachable'));
    renderApp({ token: 'owner-demo', knownRole: false });
    const nav = await mainNav();
    expect(await nav.findByRole('link', { name: /^Control Hub/ }, T)).toBeInTheDocument();
    expect(me.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('retries back off, then poll slowly', () => {
    expect([0, 1, 2, 3, 9].map(meRetryDelay)).toEqual([1000, 2000, 4000, 30_000, 30_000]);
  });
});

describe('Pro links outside the nav', () => {
  const nodes = [{ node_id: 'n1', name: 'box', role: 'hub', status: 'online' }] as unknown as Parameters<typeof buildPaletteCommands>[0]['nodes'];
  const commands = buildPaletteCommands({ now: Date.now(), apps: [], nodes, pending: [], canApprove: false });
  const proIds = ['go:nodes', 'go:backups', 'set:backups', 'node:n1'];

  it('the palette offers Pro screens to Pro roles only', () => {
    const offered = (view: 'pro' | 'simple' | 'unknown') => commands.filter((c) => paletteShows(c, view)).map((c) => c.id);
    for (const id of proIds) {
      expect(offered('pro')).toContain(id);
      expect(offered('simple')).not.toContain(id);
      expect(offered('unknown')).not.toContain(id);
    }
    expect(offered('simple')).toContain('go:home');
    expect(offered('simple')).toContain('go:settings');
  });

  it('Home for an owner links to Nodes', async () => {
    renderApp({ token: 'owner-demo' });
    const main = await screen.findByRole('main', {}, T);
    await waitFor(() => expect(main.querySelectorAll('a[href="/nodes"], a[href="/settings/backups"]').length).toBeGreaterThan(0), T);
  });
});

describe('Role-shaped UI (UX-01)', () => {
  it('Machines and Alerts are Pro screens; Approvals is not offered to a guest or child', () => {
    for (const id of ['machines', 'alerts']) {
      expect(showsNav(id, 'pro')).toBe(true);
      expect(showsNav(id, 'simple')).toBe(false);
    }
    expect(showsNav('approvals', 'simple')).toBe(false);
    expect(showsNav('approvals', 'pro')).toBe(true);
  });

  it('canDecide and canRequest come from the scopes GET /v1/me reports', () => {
    const me = (scopes: string[], capabilities: string[]) => ({ scopes, capabilities });
    expect(abilitiesFromMe(me(['*'], ['can_approve', 'can_request']))).toEqual({ canDecide: 'yes', canRequest: 'yes' });
    expect(abilitiesFromMe(me(['apps:read', 'actions:request'], ['can_request']))).toEqual({ canDecide: 'no', canRequest: 'yes' });
    expect(abilitiesFromMe(me(['instance:read', 'apps:read'], []))).toEqual({ canDecide: 'no', canRequest: 'no' });
  });

  it.each(['child-demo', 'teen-demo', 'guest-demo'])('%s gets the simple Home: my apps, my requests, family status, and no Needs you or Approvals', async (token) => {
    renderApp({ token });
    expect(await screen.findByRole('heading', { name: 'My apps' }, T)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'My requests' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Family status' })).toBeInTheDocument();
    expect(screen.queryByText(/Needs you/)).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Jobs in progress' })).not.toBeInTheDocument();
    const nav = await mainNav();
    expect(nav.queryByRole('link', { name: /^Approvals/ })).not.toBeInTheDocument();
    for (const n of ['Machines', 'Alerts']) expect(nav.queryByRole('link', { name: new RegExp(`^${n}`) })).not.toBeInTheDocument();
  });

  it('a child sees the Market install button disabled with a reason and Ask a parent', async () => {
    renderApp({ token: 'child-demo', route: '/market' });
    expect((await screen.findAllByText(/Ask a parent/, {}, T)).length).toBeGreaterThan(0);
    const install = await screen.findAllByRole('button', { name: /^Request install/ }, T);
    for (const b of install) expect(b).toBeDisabled();
    expect(screen.queryByRole('link', { name: 'Sources' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Import Compose' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Add a source' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Compose file' })).not.toBeInTheDocument();
  });

  it('an owner sees the Sources and Compose entries in the Market sidebar', async () => {
    renderApp({ token: 'owner-demo', route: '/market' });
    const nav = await screen.findByRole('navigation', { name: 'Market' }, T);
    expect(await within(nav).findByRole('link', { name: 'Add a source' }, T)).toHaveAttribute('href', '/sources');
    expect(within(nav).getByRole('link', { name: 'Compose file' })).toHaveAttribute('href', '/compose');
  });

  it('a child is told Machines is not for their role', async () => {
    renderApp({ token: 'child-demo', route: '/machines' });
    expect(await screen.findByText(/for the people who run this box/, {}, T)).toBeInTheDocument();
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
    expect(screen.getByText(AGENTS_WINDOW_NOTE)).toBeInTheDocument();
    expect(AGENTS_WINDOW_NOTE).toMatch(/latest 500 audit events/);
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

describe('Settings sections by role', () => {
  const PRO_SECTIONS = ['Users & roles', 'Agents & MCP', 'Devices & nodes'];
  it('a child sees only the personal sections and a direct link shows the role notice', async () => {
    renderApp({ token: 'child-demo', route: '/settings/users' });
    expect(await screen.findByText(/for the people who run this box/, {}, T)).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation', { name: 'Settings sections' }));
    expect(nav.getByRole('link', { name: /Appearance/ })).toBeInTheDocument();
    for (const n of PRO_SECTIONS) expect(nav.queryByRole('link', { name: new RegExp(n) })).not.toBeInTheDocument();
  });

  it('an owner sees the people and agent sections', async () => {
    renderApp({ token: 'owner-demo', route: '/settings/account' });
    const nav = within(await screen.findByRole('navigation', { name: 'Settings sections' }, T));
    for (const n of PRO_SECTIONS) expect(await nav.findByRole('link', { name: new RegExp(n) }, T)).toBeInTheDocument();
  });
});

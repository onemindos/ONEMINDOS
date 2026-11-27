// SPDX-License-Identifier: Apache-2.0
// Hide what a role cannot use (#1232, #234). A real gateway session carries no principal, so the role
// comes from GET /v1/me through useShell().role: mount with knownRole=false, once per role.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MockApi } from './api/mock';
import { ApiError } from './api/types';
import { renderApp, screensNav } from './test/helpers';

const T = { timeout: 4000 };

describe.each(['child-demo', 'teen-demo', 'guest-demo'])('%s without a known principal', (token) => {
  it('has no Approvals in the dock or Launchpad and no "connecting" pill', async () => {
    renderApp({ token, knownRole: false });
    expect(await screen.findByRole('heading', { name: 'My apps' }, T)).toBeInTheDocument();
    const dock = within(screen.getByRole('navigation', { name: 'Main' }));
    expect(dock.queryByRole('link', { name: /^Approvals/ })).not.toBeInTheDocument();
    const all = await screensNav(userEvent.setup(), T.timeout);
    expect(all.queryByRole('link', { name: /^Approvals/ })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/connecting to the hub/i)).not.toBeInTheDocument(), T);
  });

  it('a direct link to Approvals gets the calm role line, not an error', async () => {
    renderApp({ token, route: '/approvals', knownRole: false });
    expect(await screen.findByText(/Approvals are for the owner of this box/, {}, T)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Approve|Deny)/ })).not.toBeInTheDocument();
  });
});

describe('a list the hub refuses for this role', () => {
  afterEach(() => vi.restoreAllMocks());
  it('does not hold the connection pill on "connecting to the hub"', async () => {
    // A real gateway refuses a child both lists (no nodes:read, no actions:read).
    vi.spyOn(MockApi.prototype, 'nodes').mockRejectedValue(new ApiError(403, 'permission_denied', 'not for your role'));
    vi.spyOn(MockApi.prototype, 'actions').mockRejectedValue(new ApiError(403, 'permission_denied', 'not for your role'));
    renderApp({ token: 'child-demo', knownRole: false });
    expect(await screen.findByRole('heading', { name: 'My apps' }, T)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/connecting to the hub/i)).not.toBeInTheDocument(), T);
    expect(screen.getByText(/hub answering/i)).toBeInTheDocument();
  });
});

describe('adult without a known principal', () => {
  it('has no Approvals entry and no enabled Approve or Deny buttons', async () => {
    renderApp({ token: 'adult-demo', knownRole: false });
    await screen.findByRole('navigation', { name: 'Main' }, T);
    const all = await screensNav(userEvent.setup(), T.timeout);
    expect(await all.findByRole('link', { name: /^Control Hub/ }, T)).toBeInTheDocument(); // the role is known: Pro
    expect(all.queryByRole('link', { name: /^Approvals/ })).not.toBeInTheDocument();
  });

  it('a direct link shows the queue with every decision button off and the reason', async () => {
    renderApp({ token: 'adult-demo', route: '/approvals', knownRole: false });
    expect(await screen.findByText(/Only the owner can approve or deny/, {}, T)).toBeInTheDocument();
    for (const b of screen.queryAllByRole('button', { name: /^(Approve|Deny)/ })) expect(b).toBeDisabled();
    expect(screen.queryByRole('heading', { name: 'Practice an approval' })).not.toBeInTheDocument();
  });
});

describe('Home for an adult without a known principal', () => {
  it('shows no enabled Approve or Deny button', async () => {
    renderApp({ token: 'adult-demo', route: '/', knownRole: false });
    await screen.findByRole('navigation', { name: 'Main' }, T);
    // Wait until the role is known (Pro nav) and the pending approval is on the page.
    const all = await screensNav(userEvent.setup(), T.timeout);
    expect(await all.findByRole('link', { name: /^Control Hub/ }, T)).toBeInTheDocument();
    const buttons = await screen.findAllByRole('button', { name: /^(Approve|Deny)/ }, T);
    expect(buttons.length).toBeGreaterThan(0);
    for (const b of buttons) expect(b).toBeDisabled();
  });
});

describe('owner without a known principal', () => {
  it('still has Approvals and can decide', async () => {
    renderApp({ token: 'owner-demo', route: '/approvals', knownRole: false });
    const [approve] = await screen.findAllByRole('button', { name: /^Approve/ }, T);
    await waitFor(() => expect(approve).toBeEnabled(), T);
    const all = await screensNav(userEvent.setup(), T.timeout);
    expect(await all.findByRole('link', { name: /^Approvals/ }, T)).toBeInTheDocument();
  });
});

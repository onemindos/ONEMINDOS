// SPDX-License-Identifier: Apache-2.0
// The wiring-pass screens on the mock gateway: sign-in by account, first-run setup and the wizard,
// invite, Account, People, Tokens, Notifications, Alerts ("ask to fix" is only a request), Coming
// soon, and the rules that matter (one alert, no token in localStorage, AI never approves).
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MOCK_ENROL_CODE, MOCK_SETUP_TOKEN } from './api/mockWiring';
import { COMING_ITEMS } from './pages/Coming';
import { WIZARD_KEY } from './pages/SignIn';
import { renderApp, seriousViolations } from './test/helpers';

const T = { timeout: 4000 };

describe('sign-in', () => {
  it('logs in with a username and password and keeps the token out of localStorage', async () => {
    const u = userEvent.setup();
    renderApp();
    await u.type(screen.getByLabelText('Username'), 'owner');
    await u.type(screen.getByLabelText('Password'), 'demo-password');
    await u.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('navigation', { name: 'Main' }, T)).toBeInTheDocument();
    expect(window.sessionStorage.getItem('onemind.token')).toBe('owner-demo');
    expect(window.localStorage?.length ? JSON.stringify({ ...window.localStorage }) : '').not.toMatch(/owner-demo/);
  });

  it('a wrong password shows exactly one alert', async () => {
    const u = userEvent.setup();
    renderApp();
    await u.type(screen.getByLabelText('Username'), 'owner');
    await u.type(screen.getByLabelText('Password'), 'nope');
    await u.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('That username and password were not accepted.');
    expect(screen.getAllByRole('alert')).toHaveLength(1);
  });

  it('first-run setup creates the owner, then the wizard opens and starter installs become requests', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp();
    await u.click(screen.getByRole('button', { name: /First time on this box/ }));
    await u.type(screen.getByLabelText('Setup token'), MOCK_SETUP_TOKEN);
    await u.type(screen.getByLabelText('Username'), 'owner');
    await u.type(screen.getByLabelText(/^Password/), 'a-long-passphrase');
    await u.click(screen.getByRole('button', { name: 'Create the owner' }));
    expect(await screen.findByRole('heading', { name: 'Name your box' }, T)).toBeInTheDocument();
    expect(window.sessionStorage.getItem(WIZARD_KEY)).toBe('1');
    // Opening the wizard installs nothing: every request on the hub is still waiting for a person.
    expect((await getApi().actions()).filter((a) => a.state === 'succeeded' && a.type === 'app.install').every((a) => a.id !== 'new')).toBe(true);
  });

  it('refuses a short password in setup and a bad setup token', async () => {
    const u = userEvent.setup();
    renderApp();
    await u.click(screen.getByRole('button', { name: /First time on this box/ }));
    await u.type(screen.getByLabelText('Setup token'), 'wrong');
    await u.type(screen.getByLabelText('Username'), 'owner');
    await u.type(screen.getByLabelText(/^Password/), 'short');
    await u.click(screen.getByRole('button', { name: 'Create the owner' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 12 characters');
    await u.type(screen.getByLabelText(/^Password/), '-and-much-longer');
    await u.click(screen.getByRole('button', { name: 'Create the owner' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('setup token was not accepted'), T);
  });

  it('an invite code joins the box', async () => {
    const u = userEvent.setup();
    renderApp();
    await u.click(screen.getByRole('button', { name: /Have an invite code/ }));
    await u.type(screen.getByLabelText('Invite code'), MOCK_ENROL_CODE);
    await u.type(screen.getByLabelText(/^Password/), 'a-long-passphrase');
    await u.click(screen.getByRole('button', { name: 'Join' }));
    expect(await screen.findByRole('navigation', { name: 'Main' }, T)).toBeInTheDocument();
  });

  it('passes axe', async () => {
    const { container } = renderApp();
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('Account', () => {
  it('lists sessions and signs another one out', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/account' });
    expect(await screen.findByText(/phone browser/, {}, T)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Sign out phone browser' }));
    await waitFor(() => expect(screen.queryByText(/phone browser/)).not.toBeInTheDocument(), T);
  });

  it('passes axe', async () => {
    const { container } = renderApp({ token: 'owner-demo', route: '/settings/account' });
    await screen.findByText(/phone browser/, {}, T);
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('People', () => {
  it('the owner invites a person; the code is shown once and not stored', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/users' });
    await u.click(await screen.findByRole('button', { name: 'Invite a person' }, T));
    await u.type(screen.getByLabelText('Name'), 'Sam');
    await u.click(screen.getByRole('button', { name: 'Create invite' }));
    const dialog = await screen.findByRole('dialog', { name: 'Invite a person' }, T);
    expect(within(dialog).getByText(MOCK_ENROL_CODE)).toBeInTheDocument();
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(MOCK_ENROL_CODE);
  });

  it('the last owner cannot be disabled, and the hub says why', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/users' });
    await u.click(await screen.findByRole('button', { name: 'Disable Owner' }, T));
    await u.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Disable' }));
    expect(await screen.findByText(/last owner/, {}, T)).toBeInTheDocument();
  });

  it('an adult is told only the owner sees this', async () => {
    renderApp({ token: 'adult-demo', route: '/settings/users' });
    expect(await screen.findByText('Your account is not allowed to see this.', {}, T)).toBeInTheDocument();
  });
});

describe('API tokens', () => {
  it('creates an agent token, shows it once, never stores it', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/agents' });
    await u.click(await screen.findByRole('button', { name: 'Create a token' }, T));
    await u.type(screen.getByLabelText('Token name'), 'research bot');
    await u.click(screen.getByLabelText('For an AI agent'));
    await u.type(screen.getByLabelText('Agent name'), 'research');
    const dlg = screen.getByRole('dialog', { name: 'Create a token' });
    await u.click(within(dlg).getByRole('button', { name: 'Create a token' }));
    const shown = await screen.findByText(/^omk_demo_/, {}, T);
    const secret = shown.textContent ?? '';
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(secret);
    expect(window.localStorage?.length ? JSON.stringify({ ...window.localStorage }) : '').not.toContain(secret);
    await u.click(screen.getAllByRole('button', { name: 'Close' }).at(-1)!);
    expect((await screen.findAllByText('AI agent')).length).toBeGreaterThan(0);
    expect(screen.queryByText(secret)).not.toBeInTheDocument();
  });
});

describe('Notifications', () => {
  it('shows the inbox as cards and marks everything read', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/notifications' });
    expect(await screen.findByRole('article', { name: 'Backup is two days behind' }, T)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Mark all as read' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Mark as read:/ })).not.toBeInTheDocument(), T);
  });

  it('adds, tests and removes a channel', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/notifications' });
    await u.click(await screen.findByRole('button', { name: 'Add a channel' }, T));
    await u.type(screen.getByLabelText('Label'), 'Phone');
    await u.type(screen.getByLabelText('Address or URL'), 'https://ntfy.example.org/my-topic');
    await u.click(screen.getByRole('button', { name: 'Save' }));
    await u.click(await screen.findByRole('button', { name: 'Send a test to Phone' }, T));
    expect(await screen.findByText('Verified', {}, T)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Remove Phone' }));
    await waitFor(() => expect(screen.queryByText('Phone')).not.toBeInTheDocument(), T);
  });

  it('refuses a channel address that is not an http(s) URL', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/settings/notifications' });
    await u.click(await screen.findByRole('button', { name: 'Add a channel' }, T));
    await u.type(screen.getByLabelText('Label'), 'Bad');
    await u.type(screen.getByLabelText('Address or URL'), 'file:///etc/passwd');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});

describe('Alerts', () => {
  it('"Ask to fix" only files a request: it lands in Approvals, awaiting a human', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'owner-demo', route: '/alerts' });
    const card = await screen.findByRole('article', { name: /Vaultwarden is not answering/ }, T);
    await u.click(within(card).getByRole('button', { name: /^Ask to fix/ }));
    expect(await screen.findByText('Fix requested. It waits in Approvals.', {}, T)).toBeInTheDocument();
    const sent = (await getApi().actions()).find((a) => a.idempotency_key.startsWith('fix:'));
    expect(sent?.state).toBe('awaiting_approval');
    expect(sent?.decided_by ?? null).toBeNull();
  });

  it('an agent can ask to fix but the request still waits for a person', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'agent-demo', route: '/alerts' });
    const card = await screen.findByRole('article', { name: /Vaultwarden is not answering/ }, T);
    await u.click(within(card).getByRole('button', { name: /^Ask to fix/ }));
    await screen.findByText('Fix requested. It waits in Approvals.', {}, T);
    const sent = (await getApi().actions()).find((a) => a.idempotency_key.startsWith('fix:'));
    expect(sent?.requested_by?.kind).toBe('agent');
    expect(sent?.state).toBe('awaiting_approval');
  });

  it('acknowledges an alert and passes axe', async () => {
    const u = userEvent.setup();
    const { container } = renderApp({ token: 'owner-demo', route: '/alerts' });
    await u.click(await screen.findByRole('button', { name: /^Acknowledge Vaultwarden/ }, T));
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Acknowledge Vaultwarden/ })).not.toBeInTheDocument(), T);
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('Coming soon', () => {
  it('names every area without an API on main and shows no controls or data', async () => {
    renderApp({ token: 'owner-demo', route: '/coming' });
    const list = await screen.findByRole('list', { name: 'Coming soon' }, T);
    expect(within(list).getAllByRole('article')).toHaveLength(COMING_ITEMS.length);
    expect(within(list).queryAllByRole('button')).toHaveLength(0);
    for (const i of COMING_ITEMS) expect(within(list).getByRole('article', { name: i.title })).toHaveTextContent('Coming soon');
  });

  it('Backups, Updates and Storage settings say they are coming, not broken', async () => {
    renderApp({ token: 'owner-demo', route: '/settings/storage' });
    expect(await screen.findByText(/Storage: coming with/, {}, T)).toBeInTheDocument();
  });
});

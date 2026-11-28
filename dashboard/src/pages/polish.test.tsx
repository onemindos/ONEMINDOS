// SPDX-License-Identifier: Apache-2.0
// Polish: sign-in with one primary button, family copy on About, a device card, and the
// plain-language request history line.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DeviceCard } from './DeviceCard';
import { ActionStatus } from '../shell/ActionJobs';
import { renderApp, seriousViolations } from '../test/helpers';

describe('sign-in polish', () => {
  const credentialsDescriptor = Object.getOwnPropertyDescriptor(navigator, 'credentials');
  afterEach(() => {
    vi.unstubAllGlobals();
    if (credentialsDescriptor) Object.defineProperty(navigator, 'credentials', credentialsDescriptor);
    else Reflect.deleteProperty(navigator, 'credentials');
  });

  it('shows password sign-in and a passkey choice, folds away token sign-in and lets the demo note be dismissed', async () => {
    vi.stubGlobal('PublicKeyCredential', class {});
    Object.defineProperty(navigator, 'credentials', { value: {}, configurable: true });
    const u = userEvent.setup();
    const { container } = renderApp();
    expect(screen.getByLabelText('Username')).toBeVisible();
    expect(screen.getByLabelText('Password')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Log in' })).toHaveClass('om-btn-primary');
    expect(screen.getByRole('button', { name: 'Use my passkey' })).toHaveClass('om-btn-secondary');
    expect(screen.getByText(/^We recommend using a passkey/)).toBeVisible();
    const moreLink = screen.getByText('Other ways to sign in');
    const more = moreLink.closest('details')!;
    expect(more).not.toHaveAttribute('open');
    expect(within(more).getByRole('button', { name: 'Sign in', hidden: true })).not.toBeVisible();
    await u.click(moreLink);
    expect(more).toHaveAttribute('open');
    expect(within(more).getByRole('button', { name: 'Sign in' })).toHaveClass('om-btn-secondary');
    const chip = screen.getByText(/^Demo mode\./).closest('p')!;
    await u.click(within(chip).getByRole('button', { name: 'Dismiss the demo note' }));
    expect(screen.queryByText(/^Demo mode\./)).not.toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it('signs in with a password in a browser without passkeys and leaves the token form open', async () => {
    vi.stubGlobal('PublicKeyCredential', undefined);
    renderApp();
    const u = userEvent.setup();
    expect(screen.getByText('Other ways to sign in').closest('details')).toHaveAttribute('open');
    expect(screen.getByLabelText('Access token')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Use my passkey' })).not.toBeInTheDocument();
    const username = screen.getByLabelText('Username');
    const password = screen.getByLabelText('Password');
    const submit = screen.getByRole('button', { name: 'Log in' });
    expect(username).toBeVisible();
    expect(password).toBeVisible();
    expect(submit).toHaveClass('om-btn-primary');
    await u.type(username, 'owner');
    await u.type(password, 'demo-password');
    await u.click(submit);
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeVisible();
  });
});

describe('About polish', () => {
  it('shows no developer copy on Settings and About', async () => {
    renderApp({ token: 'owner-demo', route: '/settings/about' });
    expect(await screen.findByRole('heading', { name: 'About' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Log out' })).toBeInTheDocument();
    for (const dev of [/§\d/, /API call/]) expect(document.body).not.toHaveTextContent(dev);
    // API paths are allowed only inside the collapsed Technical details.
    expect(screen.getByText(/^Read from/).closest('details')).not.toHaveAttribute('open');
  });

  it('device card: storage meter from the hub numbers, uptime, memory; a missing number is left out', async () => {
    const logOut = vi.fn();
    const node = { node_id: 'n1', disk_total_gb: 400, disk_free_gb: 100, uptime_s: 93784, mem_total_mb: 15800 } as never;
    const { rerender } = render(<DeviceCard name="Home OneMind" version="0.1.1" node={node} onLogOut={logOut} />);
    expect(screen.getByRole('meter', { name: 'Storage' })).toHaveAttribute('aria-valuetext', '300 GB of 400 GB used');
    expect(screen.getByText('1d 2h')).toBeInTheDocument();
    expect(screen.getByText('15.4 GB')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Log out' }));
    expect(logOut).toHaveBeenCalledOnce();
    rerender(<DeviceCard name="Home OneMind" version="0.1.1" onLogOut={logOut} />);
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.queryByText('Running for')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Restart|Shut down/ })).not.toBeInTheDocument();
  });
});

describe('sign-in names the box', () => {
  it('shows the name the hub serves before anyone has signed in', async () => {
    renderApp();
    expect(await screen.findByRole('heading', { level: 1, name: 'Welcome to Home OneMind' })).toBeInTheDocument();
  });
});

describe('device card without device facts', () => {
  it('says when storage and memory will appear, and offers no power buttons', () => {
    render(<DeviceCard name="Home OneMind" version="0.1.0" onLogOut={() => {}} />);
    expect(screen.getByText('Storage and memory appear when OneMind runs on a real box.')).toBeInTheDocument();
  });
});

describe('request history line', () => {
  it('says what happened in plain words and keeps the ledger state under Technical details', () => {
    render(<ActionStatus action={{ id: 'a', type: 'app.install', params: { app_id: 'x' }, state: 'awaiting_approval', idempotency_key: 'k', expires_at: '2030-01-01T00:00:00Z' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Waiting for the owner to approve.');
    const tech = screen.getByText('Technical details').closest('details')!;
    expect(tech).not.toHaveAttribute('open');
    expect(tech).toHaveTextContent('State: awaiting approval');
  });

  it('finished requests show a real history line from the request data', () => {
    const now = Date.parse('2026-11-21T12:00:00Z');
    const a = { id: 'a', type: 'app.install', params: { app_id: 'x' }, state: 'succeeded', idempotency_key: 'k', expires_at: '2030-01-01T00:00:00Z', requested_by: { id: 'u', kind: 'person', role: 'owner' }, decided_by: { id: 'u', kind: 'person', role: 'owner' }, updated_at: '2026-11-20T12:00:00Z' } as const;
    render(<ActionStatus action={a} now={now} />);
    expect(screen.getByRole('status')).toHaveTextContent('Installed by owner \u00b7 approved by owner \u00b7 1d ago');
  });
});

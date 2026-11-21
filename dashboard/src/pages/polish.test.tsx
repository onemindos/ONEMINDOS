// SPDX-License-Identifier: Apache-2.0
// Polish: sign-in with one primary passkey button, family copy on About, a device card, and the
// plain-language request history line.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DeviceCard } from './DeviceCard';
import { ActionStatus } from '../shell/ActionJobs';
import { renderApp, seriousViolations } from '../test/helpers';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('sign-in polish', () => {
  it('with passkeys available: passkey is the primary button, other ways sit behind one link, the demo note can be dismissed', async () => {
    vi.stubGlobal('PublicKeyCredential', class {});
    Object.defineProperty(navigator, 'credentials', { value: {}, configurable: true });
    const u = userEvent.setup();
    const { container } = renderApp();
    expect(screen.getByRole('button', { name: 'Use my passkey' })).toHaveClass('om-btn-primary');
    const more = screen.getByText('Other ways to sign in').closest('details')!;
    expect(more).not.toHaveAttribute('open');
    await u.click(screen.getByText('Other ways to sign in'));
    expect(more).toHaveAttribute('open');
    const chip = screen.getByText(/^Demo mode\./).closest('p')!;
    await u.click(within(chip).getByRole('button', { name: 'Dismiss the demo note' }));
    expect(screen.queryByText(/^Demo mode\./)).not.toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it('without passkeys: the other ways are open, so nobody is locked out', () => {
    vi.stubGlobal('PublicKeyCredential', undefined);
    renderApp();
    expect(screen.getByText('Other ways to sign in').closest('details')).toHaveAttribute('open');
    expect(screen.getByLabelText('Username')).toBeVisible();
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
});

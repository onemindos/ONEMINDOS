// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ApprovalCard, type ActionSummary } from './ApprovalCard';
import { AppShell, PageHeader, type NavItem } from './AppShell';
import { Button } from './Button';
import { Card } from './Card';
import { Dialog } from './Dialog';
import { EmptyState } from './EmptyState';
import { NodeCard, type NodeSummary } from './NodeCard';
import { StatusPill } from './StatusPill';
import { Table } from './Table';
import { ToastProvider, TOAST_MS, useToast } from './Toast';
import { TrustCard, type AppTrust } from './TrustCard';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const later = (s: number) => new Date(NOW + s * 1000).toISOString();

async function noAxeViolations(container: Element) {
  // color-contrast needs real layout; contrast is checked on the tokens instead.
  const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
}

const node: NodeSummary = {
  node_id: 'a1',
  hostname: 'pi-garage',
  role: 'node',
  board: 'rpi5',
  arch: 'arm64',
  os: { pretty: 'Debian GNU/Linux 13 (trixie)' },
  cpus: 4,
  mem_total_mb: 8192,
  mem_available_mb: 4096,
  disk_total_gb: 120,
  disk_free_gb: 90,
  k3s: { present: true, ready: true, role: 'agent' },
  rauc: { present: true, booted_slot: 'B' },
  last_seen: ago(5),
};

const action: ActionSummary = {
  id: 'act-1',
  type: 'app.install',
  params: { app_id: 'ntfy' },
  state: 'awaiting_approval',
  expires_at: later(3600 * 20),
  created_at: ago(120),
  requested_by: { id: 'agent:hermes-agent', kind: 'agent', role: 'agent' },
  reason: 'You asked for phone alerts.',
};

const app: AppTrust = {
  id: 'ntfy',
  name: 'ntfy',
  version: '2.14.0',
  license: 'Apache-2.0',
  licenseClass: 'L1',
  tier: 'verified',
  scan: { scanned_at: ago(86_400), result: 'pass', critical: 0, high: 2, malware: 0, cosign: 'unsigned' },
  links: { docs: 'https://docs.ntfy.sh', github: 'https://github.com/binwiederhier/ntfy', website: 'javascript:alert(1)' },
  archs: ['amd64', 'arm64'],
  requires: { minMemoryMb: 128 },
  permissions: ['Open a web page on your network'],
};

describe('StatusPill', () => {
  it('always carries a word, not only a colour', () => {
    render(<StatusPill tone="ok" label="Online" detail="2 nodes" />);
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.getByText('· 2 nodes')).toBeInTheDocument();
  });
});

describe('Card and EmptyState', () => {
  it('labels the region by its title and shows the CLI line', async () => {
    const { container } = render(
      <Card title="Backups" aside={<StatusPill tone="warn" label="Not verified" />}>
        <EmptyState title="No backups yet" command="onemind backup now">
          Nothing has been backed up.
        </EmptyState>
      </Card>,
    );
    expect(screen.getByRole('region', { name: 'Backups' })).toBeInTheDocument();
    expect(screen.getByText('onemind backup now')).toBeInTheDocument();
    await noAxeViolations(container);
  });
});

describe('NodeCard', () => {
  it('shows a live node as online without the stale note', () => {
    render(<NodeCard node={node} now={NOW} />);
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.queryByText(/not live/)).toBeNull();
    expect(screen.getByRole('meter', { name: 'Memory' })).toHaveAttribute('aria-valuetext', '4.0 of 8.0 GB used');
  });

  it('never shows a stale node as live', async () => {
    const { container } = render(<NodeCard node={{ ...node, last_seen: ago(90) }} now={NOW} />);
    expect(screen.getByText('Stale')).toBeInTheDocument();
    expect(screen.getByText(/last report from 1 min ago, not live/)).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it('trusts the gateway status over its own computation', () => {
    render(<NodeCard node={{ ...node, status: 'offline' }} now={NOW} />);
    expect(screen.getByText('Offline')).toBeInTheDocument();
  });
});

describe('ApprovalCard', () => {
  it('shows requester kind, reason, exact params and the API equivalent', async () => {
    const { container } = render(<ApprovalCard action={action} now={NOW} canDecide={{ allowed: true }} onApprove={() => {}} onDeny={() => {}} />);
    expect(screen.getByRole('heading', { name: 'Install ntfy' })).toBeInTheDocument();
    expect(screen.getByText('AI agent')).toBeInTheDocument();
    expect(screen.getByText('agent:hermes-agent')).toBeInTheDocument();
    expect(screen.getByText(/expires in 20 h/)).toBeInTheDocument();
    expect(screen.getByText('POST /v1/actions/act-1/approve')).toBeInTheDocument();
    expect(container.textContent).toContain('"app_id": "ntfy"');
    await noAxeViolations(container);
  });

  it('calls approve and deny', async () => {
    const onApprove = vi.fn();
    const onDeny = vi.fn();
    render(<ApprovalCard action={action} now={NOW} canDecide={{ allowed: true }} onApprove={onApprove} onDeny={onDeny} />);
    await userEvent.click(screen.getByRole('button', { name: /^Approve/ }));
    await userEvent.click(screen.getByRole('button', { name: /^Deny/ }));
    expect(onApprove).toHaveBeenCalledWith(action);
    expect(onDeny).toHaveBeenCalledWith(action);
  });

  it('disables decisions with the reason for someone who may not decide', () => {
    render(<ApprovalCard action={action} now={NOW} canDecide={{ allowed: false, reason: 'Only the owner can approve.' }} onApprove={() => {}} />);
    const btn = screen.getByRole('button', { name: /^Approve/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription('Only the owner can approve.');
  });

  it('marks an expired request and blocks approval', () => {
    render(<ApprovalCard action={{ ...action, expires_at: ago(1) }} now={NOW} canDecide={{ allowed: true }} onApprove={() => {}} />);
    expect(screen.getByText('Expired')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Approve/ })).toBeDisabled();
  });

  it('shows the hub message for a failed action and no buttons', () => {
    render(<ApprovalCard action={{ ...action, state: 'failed', message: 'image pull failed' }} now={NOW} canDecide={{ allowed: true }} onApprove={() => {}} />);
    expect(screen.getByText(/image pull failed/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
  });
});

describe('TrustCard', () => {
  it('says it can install, drops unsafe links, and lists permissions', async () => {
    const { container } = render(<TrustCard app={app} now={NOW} placement={{ node: 'hub', reasons: ['pi-garage: needs 128 MB free, has 64 MB'] }} />);
    expect(screen.getByText('Can install')).toBeInTheDocument();
    expect(screen.getByText('hub')).toBeInTheDocument();
    const links = within(screen.getByRole('list', { name: 'Links for ntfy' })).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['https://docs.ntfy.sh/', 'https://github.com/binwiederhier/ntfy']);
    expect(screen.getByText('Open a web page on your network')).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it('explains why it cannot install', () => {
    render(<TrustCard app={{ ...app, scan: { scanned_at: ago(9 * 86_400), result: 'pass' } }} now={NOW} />);
    expect(screen.getByText('Cannot install')).toBeInTheDocument();
    expect(screen.getByText(/more than 7 days old/)).toBeInTheDocument();
  });
});

describe('Table', () => {
  const rows = [
    { id: 'b', name: 'Bravo', n: 2 },
    { id: 'a', name: 'Alpha', n: 1 },
  ];
  it('sorts by a sortable column and reports aria-sort', async () => {
    const { container } = render(
      <Table caption="Things" rows={rows} rowKey={(r) => r.id} columns={[{ key: 'name', header: 'Name', sortValue: (r) => r.name }, { key: 'n', header: 'Count', align: 'end' }]} />,
    );
    const firstCell = () => container.querySelector('tbody tr td')!.textContent;
    expect(firstCell()).toBe('Bravo');
    await userEvent.click(screen.getByRole('button', { name: /Name/ }));
    expect(firstCell()).toBe('Alpha');
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute('aria-sort', 'ascending');
    await userEvent.click(screen.getByRole('button', { name: /Name/ }));
    expect(firstCell()).toBe('Bravo');
    await noAxeViolations(container);
  });
  it('renders the empty state', () => {
    render(<Table caption="Things" rows={[]} rowKey={() => ''} columns={[]} empty={<EmptyState title="Nothing yet" />} />);
    expect(screen.getByText('Nothing yet')).toBeInTheDocument();
  });
});

describe('Dialog', () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button onClick={() => setOpen(true)}>Open</Button>
        <Dialog
          open={open}
          onClose={() => setOpen(false)}
          title="Remove ntfy?"
          role="alertdialog"
          description="Its data is kept."
          actions={
            <>
              <Button onClick={() => setOpen(false)}>Cancel</Button>
              <Button variant="danger">Remove</Button>
            </>
          }
        />
      </>
    );
  }
  it('moves focus in, traps Tab, closes on Escape and returns focus', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Open' });
    await user.click(opener);
    const dlg = screen.getByRole('alertdialog', { name: 'Remove ntfy?' });
    expect(dlg).toHaveAccessibleDescription('Its data is kept.');
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    await user.tab();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Remove' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(opener).toHaveFocus();
  });
});

describe('Toast', () => {
  function Shower({ tone }: { tone: 'ok' | 'bad' }) {
    const t = useToast();
    return <Button onClick={() => t.show({ tone, title: tone === 'ok' ? 'Request sent' : 'Install failed' })}>Go</Button>;
  }
  it('announces politely and leaves after the timeout', async () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Shower tone="ok" />
      </ToastProvider>,
    );
    act(() => screen.getByRole('button', { name: 'Go' }).click());
    expect(within(screen.getByRole('status')).getByText('Request sent')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(TOAST_MS + 10));
    expect(screen.queryByText('Request sent')).toBeNull();
    vi.useRealTimers();
  });
  it('keeps errors until dismissed, in an assertive region', async () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Shower tone="bad" />
      </ToastProvider>,
    );
    act(() => screen.getByRole('button', { name: 'Go' }).click());
    act(() => vi.advanceTimersByTime(TOAST_MS * 3));
    expect(within(screen.getByRole('alert')).getByText('Install failed')).toBeInTheDocument();
    act(() => screen.getByRole('button', { name: 'Dismiss: Install failed' }).click());
    expect(screen.queryByText('Install failed')).toBeNull();
    vi.useRealTimers();
  });
});

describe('AppShell', () => {
  const nav: NavItem[] = [
    { id: 'home', label: 'Home', href: '#/home', icon: 'home', primary: true },
    { id: 'approvals', label: 'Approvals', href: '#/approvals', icon: 'approvals', primary: true, badge: 2, badgeLabel: '2 waiting' },
    { id: 'settings', label: 'Settings', href: '#/settings', icon: 'settings', group: 'System' },
  ];
  it('marks the current page, labels badges and has one main landmark', async () => {
    const onNavigate = vi.fn((_id: string, e: { preventDefault: () => void }) => e.preventDefault());
    const { container } = render(
      <AppShell boxName="home-hub" nav={nav} current="home" onNavigate={onNavigate}>
        <PageHeader title="Home" />
      </AppShell>,
    );
    const main = within(screen.getByRole('navigation', { name: 'Main' }));
    expect(main.getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
    expect(main.getByRole('link', { name: /Approvals/ })).toHaveTextContent('2 waiting');
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument();
    await userEvent.click(main.getByRole('link', { name: 'Settings' }));
    expect(onNavigate).toHaveBeenCalledWith('settings', expect.anything());
    await noAxeViolations(container);
  });
  it('puts non-primary items under More on phones', async () => {
    render(
      <AppShell boxName="home-hub" nav={nav} current="home">
        <p>x</p>
      </AppShell>,
    );
    const more = screen.getByRole('button', { name: /More/ });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(more);
    expect(more).toHaveAttribute('aria-expanded', 'true');
  });
});

// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import type { ActionSummary } from '../components/ApprovalCard';
import type { NodeSummary } from '../components/NodeCard';
import { CommandPalette } from './CommandPalette';
import { NotificationBell, NotificationCentre } from './NotificationCentre';
import { Onboarding } from './Onboarding';
import { StateView } from './StateView';
import { buildCommands, isPaletteHotkey, moveActive, parseQuery, pushRecent, scoreCommand, searchCommands, type PaletteApp, type PaletteCommand } from './palette';
import { filterNotifications, groupByDay, markAllRead, needsYou, safeDeepLink, setRead, unreadCount, type ShellNotification } from './notifications';
import { newArrivals, toastForNotification, toastForRequest, useNotificationToasts } from './toasts';
import { viewState, isSlow } from './states';
import {
  ACCENT_IDS,
  accentVars,
  emptyDraft,
  finishIssues,
  finishRequests,
  furthestReachable,
  initCommand,
  offerable,
  selectedMemoryMb,
  slugifyBoxName,
  stepIssues,
  validateBoxName,
  type OnboardingDraft,
  type StarterApp,
} from './firstRun';
import { SHELL_CATEGORIES, category, deployClass, deployClassLabel } from './taxonomy';
import { SHELL_ICON_NAMES } from './icons';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const later = (s: number) => new Date(NOW + s * 1000).toISOString();

async function noAxeViolations(container: Element) {
  const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
}

// ---------- fixtures ----------
const apps: PaletteApp[] = [
  { id: 'home-assistant', name: 'Home Assistant', category: 'home', installed: true, status: 'running', updateAvailable: '2026.11.2' },
  { id: 'immich', name: 'Immich', category: 'files', installed: false, deployClass: 'market-community' },
  { id: 'n8n', name: 'n8n', category: 'automation', installed: false, deployClass: 'list-only' },
];
const node = (id: string, host: string, age: number, status?: NodeSummary['status']): NodeSummary => ({
  node_id: id,
  hostname: host,
  role: 'node',
  board: 'rpi5',
  arch: 'arm64',
  os: { pretty: 'OneMind OS' },
  cpus: 4,
  mem_total_mb: 8192,
  mem_available_mb: 4096,
  disk_total_gb: 100,
  disk_free_gb: 50,
  k3s: { present: true, ready: true },
  rauc: { present: true, booted_slot: 'A' },
  last_seen: ago(age),
  status,
});
const pending: ActionSummary[] = [
  { id: 'a-1', type: 'app.install', params: { app_id: 'node-red' }, state: 'awaiting_approval', expires_at: later(3600), requested_by: { id: 'agent:hermes', kind: 'agent' } },
];
const cmds = buildCommands({ now: NOW, apps, nodes: [node('n1', 'pi-garage', 5, 'online'), node('n2', 'cloud-relay', 900, 'offline')], pending, canApprove: true });

const notif = (id: string, kind: ShellNotification['kind'], ageS: number, read = false, severity: ShellNotification['severity'] = 'warning'): ShellNotification => ({
  id,
  kind,
  severity,
  source: 'test',
  title: `${kind} ${id}`,
  created: ago(ageS),
  read,
  href: '#/notifications',
});
const notes = [notif('1', 'approval_waiting', 60), notif('2', 'update_applied', 3600, true, 'info'), notif('3', 'backup_failed', 26 * 3600, false, 'critical'), notif('4', 'node_offline', 5 * 86400, true)];

// ---------- taxonomy ----------
describe('taxonomy', () => {
  it('has the 16 categories from TAXONOMY.md, each with a shell icon that exists', () => {
    expect(SHELL_CATEGORIES).toHaveLength(16);
    expect(SHELL_CATEGORIES[0]!.slug).toBe('home');
    expect(SHELL_CATEGORIES[15]!.slug).toBe('field');
    for (const c of SHELL_CATEGORIES) expect(SHELL_ICON_NAMES).toContain(c.icon);
  });
  it('only Market and private classes can be requested', () => {
    expect(deployClass('market-community').requestable).toBe(true);
    expect(deployClass('list-only').requestable).toBe(false);
    expect(deployClass('core').requestable).toBe(false);
  });
  it('never guesses a category for legacy free text', () => {
    expect(category('home-automation')).toBeUndefined();
    expect(category('field')?.name).toBe('Field & Robotics');
  });
  it('labels plugins with their class', () => {
    expect(deployClassLabel('market-verified', true)).toBe('Plugin · Verified');
  });
});

// ---------- palette ----------
describe('palette logic', () => {
  it('parses scope prefixes', () => {
    expect(parseQuery('> restart')).toEqual({ scope: 'requests', text: 'restart' });
    expect(parseQuery('@pi')).toEqual({ scope: 'nodes', text: 'pi' });
    expect(parseQuery('#media')).toEqual({ scope: 'category', text: 'media' });
  });
  it('ranks prefix over in-order letters and needs every word to match', () => {
    const c: PaletteCommand = { id: 'x', group: 'Apps', title: 'Home Assistant', icon: 'home' };
    expect(scoreCommand(c, 'home')).toBeGreaterThan(scoreCommand(c, 'hmast'));
    expect(scoreCommand(c, 'hmast')).toBeGreaterThan(0);
    expect(scoreCommand(c, 'home zzz')).toBe(0);
  });
  it('empty query shows approvals first, then recent, then navigation', () => {
    const g = searchCommands(cmds, '', { recent: ['node:n1'] });
    expect(g.map((x) => x.group)).toEqual(['Approvals', 'Recent', 'Go to']);
  });
  it('only creates requests for installable classes; list-only says why', () => {
    const immich = cmds.find((c) => c.id === 'req:install:immich')!;
    expect(immich.request).toEqual({ type: 'app.install', params: { app_id: 'immich' } });
    expect(immich.pill?.label).toBe('Community');
    expect(cmds.find((c) => c.id === 'req:install:n8n')).toBeUndefined();
    const n8n = cmds.find((c) => c.id === 'app:n8n')!;
    expect(n8n.request).toBeUndefined();
    expect(n8n.href).toBe('#/app/n8n');
    expect(n8n.subtitle).toMatch(/Link only/);
  });
  it('"> " restricts to requests, "@" to nodes, "#" to a category', () => {
    expect(searchCommands(cmds, '> home').flatMap((g) => g.items).every((c) => c.request)).toBe(true);
    expect(searchCommands(cmds, '@').flatMap((g) => g.items).every((c) => c.group === 'Nodes')).toBe(true);
    const files = searchCommands(cmds, '#files').flatMap((g) => g.items);
    expect(files.map((c) => c.id)).toEqual(['req:install:immich']);
  });
  it('marks offline nodes honestly', () => {
    expect(cmds.find((c) => c.id === 'node:n2')!.pill).toEqual({ tone: 'neutral', label: 'Offline' });
  });
  it('approvals carry the reason when the viewer cannot approve', () => {
    const agentView = buildCommands({ now: NOW, apps: [], nodes: [], pending, canApprove: false });
    expect(agentView.find((c) => c.group === 'Approvals')!.disabledReason).toMatch(/Only the owner/);
  });
  it('labels a system: principal as System, never as an agent', () => {
    const sys: ActionSummary = { ...pending[0]!, id: 'a-2', requested_by: { id: 'system:updates', kind: 'agent' } };
    const c = buildCommands({ now: NOW, apps: [], nodes: [], pending: [sys], canApprove: true }).find((x) => x.id === 'approval:a-2')!;
    expect(c.subtitle).toMatch(/^System updates/);
  });
  it('moves and wraps, recognises Cmd/Ctrl-K, keeps recent unique', () => {
    expect(moveActive(0, 'ArrowUp', 3)).toBe(2);
    expect(moveActive(2, 'ArrowDown', 3)).toBe(0);
    expect(moveActive(1, 'End', 3)).toBe(2);
    expect(moveActive(0, 'ArrowDown', 0)).toBe(-1);
    expect(isPaletteHotkey({ key: 'k', metaKey: true, ctrlKey: false, altKey: false, shiftKey: false })).toBe(true);
    expect(isPaletteHotkey({ key: 'K', metaKey: false, ctrlKey: true, altKey: false, shiftKey: false })).toBe(true);
    expect(isPaletteHotkey({ key: 'k', metaKey: false, ctrlKey: false, altKey: false, shiftKey: false })).toBe(false);
    expect(pushRecent(['a', 'b'], 'b')).toEqual(['b', 'a']);
  });
});

describe('CommandPalette', () => {
  function Harness({ onRun }: { onRun: (c: PaletteCommand) => void }) {
    const [open, setOpen] = useState(true);
    return <CommandPalette open={open} onClose={() => setOpen(false)} commands={cmds} onRun={onRun} />;
  }

  it('is a combobox dialog, keyboard driven, and runs the active option', async () => {
    const onRun = vi.fn();
    const user = userEvent.setup();
    render(<Harness onRun={onRun} />);
    const box = screen.getByRole('combobox');
    expect(box).toHaveFocus();
    await user.type(box, 'immich');
    const first = screen.getAllByRole('option')[0]!;
    expect(box).toHaveAttribute('aria-activedescendant', first.id);
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText(/Same as/).parentElement).toHaveTextContent('app.install');
    await user.keyboard('{Enter}');
    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ id: 'req:install:immich' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('does not run a blocked option; it reads the reason instead', async () => {
    const onRun = vi.fn();
    const user = userEvent.setup();
    const blocked: PaletteCommand = { id: 'b', group: 'Requests', title: 'Request restore of backups', icon: 'backups', request: { type: 'backup.restore', params: {} }, disabledReason: 'Only the owner can request a restore.' };
    render(<CommandPalette open onClose={() => {}} commands={[blocked]} onRun={onRun} />);
    await user.type(screen.getByRole('combobox'), 'restore');
    expect(screen.getByRole('option')).toHaveAttribute('aria-disabled', 'true');
    await user.keyboard('{Enter}');
    expect(onRun).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent(/Only the owner/);
  });

  it('Escape clears the query first, then closes', async () => {
    const user = userEvent.setup();
    render(<Harness onRun={vi.fn()} />);
    await user.type(screen.getByRole('combobox'), 'pi');
    await user.keyboard('{Escape}');
    expect(screen.getByRole('combobox')).toHaveValue('');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows an honest empty result and has no axe violations', async () => {
    const user = userEvent.setup();
    render(<Harness onRun={vi.fn()} />);
    await noAxeViolations(document.body);
    await user.type(screen.getByRole('combobox'), 'qqqqzz');
    expect(screen.getByText(/No matches for/)).toBeInTheDocument();
  });

  it('says when results are from a stale report', () => {
    render(<CommandPalette open onClose={() => {}} commands={cmds} onRun={() => {}} state="stale" ageSeconds={180} />);
    expect(screen.getByText(/last report 3 min ago/)).toBeInTheDocument();
  });
});

// ---------- notifications ----------
describe('notification logic', () => {
  it('counts, filters and finds what needs a person', () => {
    expect(unreadCount(notes)).toBe(2);
    expect(filterNotifications(notes, 'unread').map((n) => n.id)).toEqual(['1', '3']);
    expect(notes.filter(needsYou).map((n) => n.id)).toEqual(['1', '3']);
  });
  it('groups by UTC day, newest first', () => {
    expect(groupByDay(notes, NOW).map((g) => g.label)).toEqual(['Today', 'Yesterday', '7 Nov 2026']);
  });
  it('marks read without mutating', () => {
    const r = setRead(notes, ['1']);
    expect(r.find((n) => n.id === '1')!.read).toBe(true);
    expect(notes[0]!.read).toBe(false);
    expect(unreadCount(markAllRead(notes))).toBe(0);
  });
  it('only follows in-app deep links', () => {
    expect(safeDeepLink('#/approvals/a-1')).toBe('#/approvals/a-1');
    expect(safeDeepLink('/app/immich')).toBe('/app/immich');
    expect(safeDeepLink('javascript:alert(1)')).toBe('#/notifications');
    expect(safeDeepLink('//evil.example/x')).toBe('#/notifications');
    expect(safeDeepLink('https://evil.example')).toBe('#/notifications');
  });
});

describe('NotificationCentre', () => {
  function Harness() {
    const [items, setItems] = useState(notes);
    return <NotificationBell items={items} now={NOW} onSetRead={(ids, r) => setItems((x) => setRead(x, ids, r))} onReadAll={() => setItems(markAllRead)} />;
  }

  it('bell announces unread count, opens, filters, marks read and closes on Escape', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const bell = screen.getByRole('button', { name: 'Notifications, 2 unread' });
    await user.click(bell);
    expect(bell).toHaveAttribute('aria-expanded', 'true');
    const centre = screen.getByRole('region', { name: 'Notifications' });
    await user.click(within(centre).getByRole('radio', { name: /Needs you/ }));
    expect(within(centre).getAllByRole('listitem')).toHaveLength(2);
    await user.click(within(centre).getByRole('button', { name: /Mark as read: approval_waiting 1/ }));
    expect(screen.getByRole('button', { name: 'Notifications, 1 unread' })).toBeInTheDocument();
    await user.click(within(centre).getByRole('button', { name: 'Mark all read' }));
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    await noAxeViolations(document.body);
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Notifications' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Notifications' })).toHaveFocus();
  });

  it('shows empty, loading, error and stale honestly', () => {
    const { rerender } = render(<NotificationCentre items={[]} now={NOW} onSetRead={() => {}} onReadAll={() => {}} />);
    expect(screen.getByText('You are all caught up')).toBeInTheDocument();
    rerender(<NotificationCentre items={[]} now={NOW} state="loading" onSetRead={() => {}} onReadAll={() => {}} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading notifications');
    rerender(<NotificationCentre items={[]} now={NOW} state="error" error={{ error: 'unreachable', message: 'timeout' }} onSetRead={() => {}} onReadAll={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('The hub is not answering');
    rerender(<NotificationCentre items={notes} now={NOW} state="stale" ageSeconds={240} onSetRead={() => {}} onReadAll={() => {}} />);
    expect(screen.getByText(/last report from 4 min ago/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark all read' })).toBeDisabled();
  });
});

// ---------- toasts ----------
describe('toasts', () => {
  it('maps notifications and requests to toasts with deep links', () => {
    const nav = vi.fn();
    const t = toastForNotification(notes[2]!, nav);
    expect(t.tone).toBe('bad');
    t.action!.onClick();
    expect(nav).toHaveBeenCalledWith('#/notifications');
    const r = toastForRequest('Install Immich', 'a 9', nav);
    expect(r.body).toMatch(/waits in Approvals/);
    r.action!.onClick();
    expect(nav).toHaveBeenLastCalledWith('#/approvals/a%209');
  });
  it('only new unread arrivals toast; the first load does not', () => {
    const first = newArrivals(null, notes);
    expect(first.fresh).toEqual([]);
    const next = newArrivals(first.seen, [notif('9', 'app_rolled_back', 1), ...notes]);
    expect(next.fresh.map((n) => n.id)).toEqual(['9']);
  });
  it('useNotificationToasts shows arrivals after mount', () => {
    function Feed({ items }: { items: ShellNotification[] }) {
      useNotificationToasts(items, () => {});
      return null;
    }
    const { rerender } = render(
      <ToastProvider>
        <Feed items={notes} />
      </ToastProvider>,
    );
    expect(screen.queryByText('app_rolled_back 9')).toBeNull();
    act(() => {
      rerender(
        <ToastProvider>
          <Feed items={[notif('9', 'app_rolled_back', 1, false, 'critical'), ...notes]} />
        </ToastProvider>,
      );
    });
    expect(screen.getByRole('alert')).toHaveTextContent('app_rolled_back 9');
  });
});

// ---------- states ----------
describe('state system', () => {
  it('resolves the state in the documented order', () => {
    expect(viewState({ loading: true }, { now: NOW })).toBe('loading');
    expect(viewState({ data: [] }, { now: NOW })).toBe('empty');
    expect(viewState({ data: [1], observedAt: ago(2) }, { now: NOW })).toBe('ready');
    expect(viewState({ data: [1], observedAt: ago(60) }, { now: NOW })).toBe('stale');
    expect(viewState({ data: [1], observedAt: ago(600) }, { now: NOW })).toBe('offline');
    expect(viewState({ data: [1], error: { error: 'unreachable', message: '' } }, { now: NOW })).toBe('offline');
    expect(viewState({ error: { error: 'not_found', message: '' } }, { now: NOW })).toBe('error');
    expect(viewState({ data: [1], error: { error: 'permission_denied', message: '' } }, { now: NOW })).toBe('forbidden');
    expect(isSlow(NOW - 11_000, NOW)).toBe(true);
  });
  it('renders every state accessibly', async () => {
    const { container, rerender } = render(<StateView state="empty" empty="approvals" />);
    expect(screen.getByRole('note', { name: 'Nothing is waiting for you' })).toBeInTheDocument();
    expect(screen.getByText('GET /v1/actions?state=awaiting_approval')).toBeInTheDocument();
    await noAxeViolations(container);
    rerender(<StateView state="error" error={{ error: 'conflict', message: 'install running' }} onRetry={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('conflict');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    rerender(<StateView state="loading" what="Loading apps" slow />);
    expect(screen.getByRole('status')).toHaveTextContent(/taking longer/);
    rerender(<StateView state="forbidden" forbiddenReason="Only the owner can see backups." />);
    expect(screen.getByText('Only the owner can see backups.')).toBeInTheDocument();
    rerender(
      <StateView state="offline" ageSeconds={3600}>
        <p>last values</p>
      </StateView>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Offline. Showing the last report from 1 h ago.');
    expect(screen.getByText('last values')).toBeInTheDocument();
    await noAxeViolations(container);
  });
});

// ---------- onboarding ----------
const starter: StarterApp[] = [
  { id: 'home-assistant', name: 'Home Assistant', tagline: 'Smart home hub', category: 'home', deployClass: 'market-verified', minMemoryMb: 1024, recommended: true },
  { id: 'immich', name: 'Immich', tagline: 'Photos', category: 'files', deployClass: 'market-community', minMemoryMb: 4096 },
  { id: 'n8n', name: 'n8n', tagline: 'Workflows', category: 'automation', deployClass: 'list-only', minMemoryMb: 512 },
];
const complete: OnboardingDraft = {
  ...emptyDraft('Europe/London'),
  boxName: 'home-hub',
  ownerName: 'Dana',
  passkey: 'registered',
  starterApps: ['home-assistant'],
  backup: { destination: 'usb', kitSaved: true },
};

describe('first-run logic', () => {
  it('validates box names as DNS labels and slugifies', () => {
    expect(validateBoxName('home-hub')).toBeNull();
    expect(validateBoxName('Home Hub')).toMatch(/lowercase/);
    expect(validateBoxName('-hub')).toMatch(/Start and end/);
    expect(validateBoxName('a'.repeat(64))).toMatch(/63/);
    expect(slugifyBoxName("Dana's Home Hub!")).toBe('danas-home-hub');
  });
  it('the emergency kit and the passkey cannot be skipped', () => {
    expect(stepIssues('backups', { ...complete, backup: { destination: 'later', kitSaved: false } })).toHaveLength(1);
    expect(stepIssues('backups', { ...complete, backup: { destination: 'later', kitSaved: true } })).toEqual([]);
    expect(stepIssues('owner', { ...complete, passkey: 'failed' })[0]).toMatch(/passkey/);
    expect(finishIssues(complete)).toEqual([]);
    expect(furthestReachable(emptyDraft())).toBe(0);
    expect(furthestReachable(complete)).toBe(5);
  });
  it('starter apps become requests, never installs; only installable classes are offered', () => {
    expect(finishRequests(complete)).toEqual([{ type: 'app.install', params: { app_id: 'home-assistant' } }]);
    expect(offerable(starter).map((a) => a.id)).toEqual(['home-assistant', 'immich']);
    expect(selectedMemoryMb(starter, ['home-assistant', 'immich'])).toBe(5120);
  });
  it('prints the headless twin with safe quoting', () => {
    expect(initCommand({ ...complete, ownerName: "Dana O'Neil", accent: 'orchid' })).toBe(
      "onemind init --name home-hub --timezone Europe/London --owner 'Dana O'\\''Neil' --accent orchid --backup usb --request-apps home-assistant",
    );
  });
  it('re-tints with the Appearance presets in both themes; the brand accent is the default', () => {
    expect(ACCENT_IDS).toContain('onemind');
    expect(ACCENT_IDS).toContain('teal');
    expect(accentVars('onemind')).toEqual({});
    const v = accentVars('orchid') as Record<string, string>;
    expect(v['--om-color-accent']).toMatch(/^light-dark\(#[0-9a-f]{6}, #[0-9a-f]{6}\)$/i);
    expect(Object.keys(v)).toEqual(['--om-color-accent', '--om-color-accent-hover', '--om-color-accent-text', '--om-color-accent-soft']);
  });
});

describe('Onboarding', () => {
  it('walks every step by keyboard, blocks on the kit, and finishes with requests', async () => {
    const onFinish = vi.fn();
    const user = userEvent.setup();
    render(<Onboarding apps={starter} initial={{ timeZone: 'Europe/London' }} timeZones={['Europe/London', 'UTC']} onCreatePasskey={async () => true} onThemeChange={() => {}} onFinish={onFinish} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Name your box' })).toBeInTheDocument();
    await noAxeViolations(document.body);

    await user.click(screen.getByRole('button', { name: /Continue/ }));
    expect(screen.getByRole('alert')).toHaveTextContent('Give your box a name.');
    await user.type(screen.getByLabelText('Box name'), 'Home Hub');
    expect(screen.getByLabelText('Box name')).toHaveValue('home-hub');
    await user.click(screen.getByRole('button', { name: /Continue/ }));

    const h = screen.getByRole('heading', { level: 1, name: 'Create the owner' });
    expect(h).toHaveFocus();
    await user.type(screen.getByLabelText('Your name'), 'Dana');
    await user.click(screen.getByRole('button', { name: /Create passkey/ }));
    expect(await screen.findByText('Passkey saved')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Continue/ }));

    await user.click(screen.getByRole('radio', { name: /Orchid/ }));
    await noAxeViolations(document.body);
    await user.click(screen.getByRole('button', { name: /Continue/ }));

    expect(screen.queryByText('n8n')).toBeNull(); // list-only is never offered
    await user.click(screen.getByRole('button', { name: /Files & Photos/ }));
    await user.click(screen.getByRole('checkbox', { name: /Immich/ }));
    expect(screen.getByText(/Each becomes an install request/)).toBeInTheDocument();
    await noAxeViolations(document.body);
    await user.click(screen.getByRole('button', { name: /Continue/ }));

    await user.click(screen.getByRole('button', { name: /Finish setup/ }));
    expect(screen.getByRole('alert')).toHaveTextContent(/emergency kit/);
    expect(screen.getByRole('checkbox', { name: /printed it/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /Download emergency kit/ }));
    await user.click(screen.getByRole('checkbox', { name: /printed it/ }));
    await noAxeViolations(document.body);
    await user.click(screen.getByRole('button', { name: /Finish setup/ }));

    expect(screen.getByRole('heading', { level: 1, name: 'You are all set' })).toBeInTheDocument();
    expect(screen.getByText(/1 install request will wait/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Go to Home/ }));
    expect(onFinish).toHaveBeenCalledWith(
      expect.objectContaining({ boxName: 'home-hub', accent: 'orchid', ownerName: 'Dana' }),
      [{ type: 'app.install', params: { app_id: 'immich' } }],
    );
  });
});

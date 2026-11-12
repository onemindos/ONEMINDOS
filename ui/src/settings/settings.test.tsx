// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { describe, expect, it, vi } from 'vitest';
import type { ActionSummary } from '../components/ApprovalCard';
import { ToastProvider } from '../components/Toast';
import { ApprovalsBoard, EffectsCard } from './ApprovalsBoard';
import { AuditTimeline } from './AuditTimeline';
import { chainBadge, filterAudit, groupByDay, groupEffects, inQuietHours, minutesOf, planRisk, restoreBadge, tokenState, usageByCategory, byDeployClass, matchSection } from './logic';
import { Async } from './primitives';
import { AccountSection, AgentsSection, UsersSection } from './SectionsAccess';
import { AutomationSection, BackupsSection, NotificationsSection, UpdatesSection } from './SectionsCare';
import { AboutSection, DevicesSection, NetworkSection, StorageSection } from './SectionsSystem';
import { SettingsLayout } from './SettingsLayout';
import type { AccountData, ActionPlan, AgentsData, AuditEntry, BackupsData, Loadable } from './types';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const later = (s: number) => new Date(NOW + s * 1000).toISOString();
const D = 86_400;
const ready = <T,>(data: T, stale = false): Loadable<T> => ({ status: 'ready', data, asOf: ago(stale ? 420 : 2), stale });

async function noAxeViolations(container: Element) {
  const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
}

describe('settings logic', () => {
  it('judges the last verified restore by age and result', () => {
    expect(restoreBadge(null, NOW)).toMatchObject({ tone: 'bad', label: 'Never verified' });
    expect(restoreBadge({ at: ago(D), result: 'ok' }, NOW).tone).toBe('ok');
    expect(restoreBadge({ at: ago(10 * D), result: 'ok' }, NOW).tone).toBe('warn');
    expect(restoreBadge({ at: ago(40 * D), result: 'ok' }, NOW).tone).toBe('bad');
    expect(restoreBadge({ at: ago(D), result: 'failed' }, NOW).label).toBe('Restore test failed');
    expect(restoreBadge({ at: 'nonsense', result: 'ok' }, NOW).label).toBe('Unknown');
  });

  it('reports the audit chain honestly, including an old check', () => {
    const base = { first: 1, last: 1289, checked_at: ago(120) };
    expect(chainBadge({ ...base, state: 'verified' }, NOW)).toMatchObject({ tone: 'ok', label: 'Chain verified' });
    expect(chainBadge({ ...base, state: 'verified', checked_at: ago(2 * D) }, NOW).tone).toBe('warn');
    const broken = chainBadge({ ...base, state: 'broken', broken_at: 1203 }, NOW);
    expect(broken.tone).toBe('bad');
    expect(broken.detail).toContain('#1203');
  });

  it('derives token state from expiry and revocation', () => {
    expect(tokenState({ expires_at: null, revoked_at: null }, NOW)).toBe('active');
    expect(tokenState({ expires_at: later(3 * D), revoked_at: null }, NOW)).toBe('expiring');
    expect(tokenState({ expires_at: later(30 * D), revoked_at: null }, NOW)).toBe('active');
    expect(tokenState({ expires_at: ago(1), revoked_at: null }, NOW)).toBe('expired');
    expect(tokenState({ expires_at: later(30 * D), revoked_at: ago(5) }, NOW)).toBe('revoked');
  });

  it('handles quiet hours across midnight and bad input', () => {
    const q = { enabled: true, start: '22:00', end: '07:00' };
    expect(inQuietHours(q, minutesOf('23:30'))).toBe(true);
    expect(inQuietHours(q, minutesOf('06:59'))).toBe(true);
    expect(inQuietHours(q, minutesOf('07:00'))).toBe(false);
    expect(inQuietHours(q, minutesOf('15:00'))).toBe(false);
    expect(inQuietHours({ ...q, start: '13:00', end: '14:00' }, minutesOf('13:30'))).toBe(true);
    expect(inQuietHours({ ...q, enabled: false }, minutesOf('23:30'))).toBe(false);
    expect(inQuietHours({ ...q, start: '25:00' }, minutesOf('23:30'))).toBe(false);
    expect(minutesOf('7am')).toBeNaN();
  });

  it('groups effects in reading order with the riskiest first, and rates the plan', () => {
    const effects: ActionPlan['effects'] = [
      { kind: 'image', label: 'img', risk: 'low' },
      { kind: 'port', label: 'lan', risk: 'low' },
      { kind: 'exposure', label: 'internet', risk: 'high' },
      { kind: 'data-delete', label: 'wipe', risk: 'high' },
    ];
    const g = groupEffects(effects);
    expect(g.map((x) => x.title)).toEqual(['Deletes', 'Reachable from', 'Downloads']);
    expect(g[1]!.items[0]!.label).toBe('internet');
    expect(planRisk({ effects, undo: 'reversible' })).toBe('high');
    expect(planRisk({ effects: [], undo: 'one-way' })).toBe('medium');
    expect(planRisk({ effects: [], undo: 'reversible', placement: { node: 'a', fits: true, reason: '', stale: true } })).toBe('medium');
    expect(planRisk({ effects: [], undo: 'reversible' })).toBe('low');
  });

  it('filters and groups the audit timeline by actor, text and UTC day', () => {
    const e = (seq: number, at: string, kind: AuditEntry['actor']['kind'], text: string): AuditEntry => ({ seq, at, actor: { id: `${kind}:x`, kind }, kind: 'request', text, hash: 'abc' });
    const entries = [e(3, ago(60), 'agent', 'requested Install node-red'), e(2, ago(D), 'person', 'approved'), e(1, ago(3 * D), 'device', 'joined'), e(0, 'bad', 'system', 'x')];
    expect(filterAudit(entries, 'agent').map((x) => x.seq)).toEqual([3]);
    expect(filterAudit(entries, 'system').map((x) => x.seq)).toEqual([1, 0]);
    expect(filterAudit(entries, 'all', 'node-red').map((x) => x.seq)).toEqual([3]);
    expect(filterAudit(entries, 'all', '#2').map((x) => x.seq)).toEqual([2]);
    const days = groupByDay(entries, NOW);
    expect(days.map((d) => d.label).slice(0, 2)).toEqual(['Today', 'Yesterday']);
    expect(days[2]!.label).toMatch(/Monday,? 9 Nov/);
  });

  it('sums storage by category and groups by deployment class', () => {
    const u = usageByCategory(
      [
        { category: 'files', used_gb: 60 },
        { category: 'home', used_gb: 20 },
        { category: 'home', used_gb: 9 },
        { category: 'ai', used_gb: 9 },
        { category: 'news', used_gb: 1 },
        { category: 'field', used_gb: 2 },
        { category: 'notes', used_gb: -5 },
      ],
      3,
    );
    expect(u.map((x) => [x.label, x.gb])).toEqual([
      ['Files & Photos', 60],
      ['Home & IoT', 29],
      ['AI & Agents', 9],
      ['Everything else', 3],
    ]);
    const g = byDeployClass([
      { id: 1, deploy_class: 'private' as const },
      { id: 2, deploy_class: 'market-verified' as const },
      { id: 3, deploy_class: 'core' as const },
    ]);
    expect(g.map((x) => x.cls)).toEqual(['core', 'market-verified', 'private']);
  });

  it('matches settings search on labels and keywords', () => {
    expect(matchSection({ label: 'Backups', keywords: ['restore'] }, 'RESTORE')).toBe(true);
    expect(matchSection({ label: 'Backups' }, 'wifi')).toBe(false);
    expect(matchSection({ label: 'Backups' }, '  ')).toBe(true);
  });
});

describe('Async states', () => {
  const child = (d: string[]) => <p>{d.join(',')}</p>;
  it('shows a labelled skeleton, an error with its code and retry, stale with age, empty, and content', async () => {
    const retry = vi.fn();
    const { rerender, container } = render(<Async value={{ status: 'loading' }} label="sessions" now={NOW}>{child}</Async>);
    expect(screen.getByRole('status')).toHaveTextContent('Loading sessions');
    rerender(
      <Async value={{ status: 'error', error: { error: 'unavailable', message: 'timeout' } }} label="sessions" now={NOW} onRetry={retry}>
        {child}
      </Async>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load sessions');
    expect(screen.getByRole('alert')).toHaveTextContent('unavailable');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalled();
    rerender(<Async value={ready(['a'], true)} label="sessions" now={NOW}>{child}</Async>);
    expect(screen.getByText('Last known')).toBeInTheDocument();
    expect(screen.getByText(/not live/)).toBeInTheDocument();
    rerender(<Async value={ready([] as string[])} label="sessions" now={NOW} isEmpty={(d) => d.length === 0} empty={<p>none</p>}>{child}</Async>);
    expect(screen.getByText('none')).toBeInTheDocument();
    rerender(<Async value={ready(['a', 'b'])} label="sessions" now={NOW}>{child}</Async>);
    expect(screen.getByText('a,b')).toBeInTheDocument();
    await noAxeViolations(container);
  });
});

const account: AccountData = {
  person: { id: 'person:owner', name: 'Owner', role: 'owner' },
  passkeysAvailable: false,
  passkeys: [],
  totp: false,
  requirePasskeyApproval: true,
  sessions: [
    { id: 's1', device: 'Laptop', client: 'browser', created_at: ago(D), last_seen_at: ago(5), current: true, approval: 'passkey' },
    { id: 's2', device: 'Phone', client: 'phone', created_at: ago(D), last_seen_at: ago(60), approval: 'passkey' },
  ],
  tokens: [{ id: 'tok_1', name: 'script', principal: 'person:owner', kind: 'pat', created_at: ago(D), expires_at: later(2 * D), last_used_at: null, revoked_at: null }],
};

describe('settings sections', () => {
  it('account: passkeys placeholder, instant sign-out and token revoke, requests for adding power', async () => {
    const onIntent = vi.fn();
    const { container } = render(<AccountSection data={ready(account)} now={NOW} onIntent={onIntent} />);
    expect(screen.getByText(/Passkeys arrive with the next gateway release/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a passkey' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(onIntent).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'auth.session.revoke', mode: 'instant', call: 'DELETE /v1/auth/sessions/s2' }));
    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    expect(onIntent).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'token.revoke', mode: 'instant' }));
    await userEvent.click(screen.getByRole('switch', { name: 'Authenticator app codes' }));
    expect(onIntent).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'auth.totp.set', mode: 'request' }));
    expect(screen.getByText('Expires soon')).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it('pauses every control while the data is stale', () => {
    render(<AccountSection data={ready(account, true)} now={NOW} onIntent={vi.fn()} />);
    expect(screen.getByRole('switch', { name: 'Authenticator app codes' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeDisabled();
    expect(screen.getByText(/Changes are paused while the hub is not answering/)).toBeInTheDocument();
  });

  it('agents: revoke all needs the typed word and is instant; resume is a request', async () => {
    const onIntent = vi.fn();
    const data: AgentsData = {
      mcp: { enabled: true, path: '/mcp' },
      agents: [
        { id: 'agent:a', name: 'A', state: 'active', tools: [{ name: 'list_apps', kind: 'read' }], tokens: 1, last_active_at: ago(60), week: { asked: 1, approved: 1, denied: 0 }, pending: 2 },
        { id: 'agent:b', name: 'B', state: 'suspended', tools: [], tokens: 0, last_active_at: null, week: { asked: 0, approved: 0, denied: 0 }, pending: 0 },
      ],
    };
    const { container } = render(<AgentsSection data={ready(data)} now={NOW} onIntent={onIntent} />);
    await noAxeViolations(container);
    await userEvent.click(screen.getByRole('button', { name: 'Request resume' }));
    expect(onIntent).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'agent.resume', mode: 'request' }));
    await userEvent.click(screen.getByRole('button', { name: 'Revoke all' }));
    const dlg = screen.getByRole('alertdialog', { name: 'Revoke all agent access?' });
    expect(dlg).toHaveTextContent('2 waiting requests are cancelled');
    const confirm = within(dlg).getByRole('button', { name: 'Revoke all' });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dlg).getByLabelText('Type REVOKE to confirm'), 'revoke');
    await userEvent.click(confirm);
    expect(onIntent).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'agents.suspend_all', mode: 'instant' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('backups: restore asks for scope and becomes a request', async () => {
    const onIntent = vi.fn();
    const data: BackupsData = {
      destinations: [{ id: 'u', name: 'USB', kind: 'usb', last_success_at: ago(60), state: 'current', used_gb: 10 }],
      schedule: { every: 'daily', at: '02:30', keep: '7 daily' },
      lastVerifiedRestore: null,
      snapshots: [{ id: 'snap1', at: ago(60), size_gb: 1, verified: 'untested' }],
      emergencyKit: { saved: false, keys: 0, of: 3 },
    };
    render(<BackupsSection data={ready(data)} now={NOW} onIntent={onIntent} />);
    expect(screen.getByText('Never verified')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Restore…' }));
    const dlg = screen.getByRole('alertdialog', { name: 'Request a restore' });
    await userEvent.click(within(dlg).getByRole('radio', { name: /The whole box/ }));
    await userEvent.click(within(dlg).getByRole('button', { name: 'Request restore' }));
    expect(onIntent).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'backup.restore', mode: 'request', params: { snapshot: 'snap1', scope: 'box' } }));
  });

  it('every section renders loading, error and its empty state without axe violations', async () => {
    const loading: Loadable<never> = { status: 'loading' };
    const error: Loadable<never> = { status: 'error', error: { error: 'permission_denied', message: 'owner only' } };
    const sections = [AccountSection, UsersSection, AgentsSection, DevicesSection, NetworkSection, StorageSection, AboutSection, BackupsSection, UpdatesSection, NotificationsSection, AutomationSection];
    for (const S of sections) {
      const a = render(<S data={loading} now={NOW} onIntent={vi.fn()} />);
      expect(a.getByRole('status')).toHaveTextContent('Loading');
      a.unmount();
      const b = render(<S data={error} now={NOW} onIntent={vi.fn()} />);
      expect(b.getByRole('alert')).toHaveTextContent('Your account cannot see this');
      await noAxeViolations(b.container);
      b.unmount();
    }
    const u = render(<UsersSection data={ready([])} now={NOW} onIntent={vi.fn()} />);
    expect(u.getByText('Only you so far')).toBeInTheDocument();
    u.unmount();
    const r = render(<AutomationSection data={ready([])} now={NOW} onIntent={vi.fn()} />);
    expect(r.getByText('No rules yet')).toBeInTheDocument();
  });
});

describe('SettingsLayout', () => {
  it('marks the current section, searches by keyword, and offers a way back on phones', async () => {
    const { container } = render(
      <SettingsLayout current="backups" explicit hrefFor={(id) => `#/s/${id}`} indexHref="#/s" hints={{ backups: { tone: 'warn', label: 'Verify soon' } }}>
        <p>content</p>
      </SettingsLayout>,
    );
    const nav = screen.getByRole('navigation', { name: 'Settings sections' });
    expect(within(nav).getByRole('link', { name: /Backups/ })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: /Backups/ })).toHaveTextContent('Verify soon');
    expect(screen.getByRole('link', { name: 'All settings' })).toHaveAttribute('href', '#/s');
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search settings' }), 'passkey');
    expect(within(nav).getAllByRole('link')).toHaveLength(1);
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Search settings' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search settings' }), 'zzz');
    expect(screen.getByText(/No setting matches/)).toBeInTheDocument();
    await noAxeViolations(container);
  });
});

describe('AuditTimeline', () => {
  const data = {
    verify: { state: 'verified' as const, first: 1, last: 3, checked_at: ago(60) },
    entries: [
      { seq: 3, at: ago(60), actor: { id: 'agent:hermes', kind: 'agent' as const }, kind: 'request' as const, text: 'requested Install x', hash: 'aa' },
      { seq: 2, at: ago(D), actor: { id: 'person:owner', kind: 'person' as const }, kind: 'decision' as const, text: 'approved y', hash: 'bb', result: 'ok' as const, resultLabel: 'Done' },
    ],
  };
  it('shows chain verified, filters by actor and groups by day', async () => {
    const { container } = render(<AuditTimeline data={ready(data)} now={NOW} onVerify={vi.fn()} />);
    expect(screen.getByText('Chain verified')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Today' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Yesterday' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Agents' }));
    expect(screen.getByRole('button', { name: 'Agents' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('approved y')).not.toBeInTheDocument();
    await noAxeViolations(container);
  });
  it('raises a broken chain as an alert', () => {
    render(<AuditTimeline data={ready({ ...data, verify: { ...data.verify, state: 'broken', broken_at: 2 } })} now={NOW} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Chain broken');
  });
});

describe('Approvals board and effects card', () => {
  const a = (id: string, who: { id: string; kind: 'person' | 'agent' }, type = 'app.install'): ActionSummary => ({
    id,
    type,
    params: { app_id: id },
    state: 'awaiting_approval',
    created_at: ago(60),
    expires_at: later(3600),
    requested_by: who,
  });
  const plan: ActionPlan = {
    action_id: 'x1',
    plan_hash: 'sha256:abcd',
    computed_at: ago(30),
    app: { id: 'x1', name: 'X One', category: 'home', deploy_class: 'market-community', plugin: true },
    placement: { node: 'hub', fits: true, reason: 'fits' },
    effects: [
      { kind: 'exposure', label: 'Anyone on the internet', risk: 'high' },
      { kind: 'image', label: 'img 1.0', risk: 'low' },
    ],
    undo: 'reversible',
  };

  it('renders the gateway plan with category, class, groups, risk and plan hash', async () => {
    const { container } = render(<EffectsCard plan={ready(plan)} now={NOW} />);
    expect(screen.getByText('High impact')).toBeInTheDocument();
    expect(screen.getByText('Home & IoT')).toBeInTheDocument();
    expect(screen.getByText('Community')).toBeInTheDocument();
    expect(screen.getByText('Plugin: adds to OneMind')).toBeInTheDocument();
    expect(screen.getByText('Reachable from')).toBeInTheDocument();
    expect(screen.getByText('sha256:abcd')).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it('says so when the plan could not be computed', () => {
    render(<EffectsCard plan={{ status: 'error', error: { error: 'conflict', message: 'catalog changed' } }} now={NOW} />);
    expect(screen.getByRole('alert')).toHaveTextContent('could not compute');
  });

  it('selects requests from the queue, filters by requester, and approves through the card', async () => {
    const onApprove = vi.fn();
    const list = [a('x1', { id: 'agent:hermes', kind: 'agent' }), a('x2', { id: 'person:alex', kind: 'person' }), a('x3', { id: 'system:updates', kind: 'agent' }, 'app.update')];
    const { container } = render(
      <ToastProvider>
        <ApprovalsBoard actions={ready(list)} plans={{ x1: ready(plan) }} now={NOW} canDecide={{ allowed: true }} onApprove={onApprove} />
      </ToastProvider>,
    );
    const queue = screen.getByRole('list', { name: 'Waiting requests' });
    expect(within(queue).getAllByRole('button')[0]).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('heading', { name: 'Install x1' })).toBeInTheDocument();
    await userEvent.click(within(queue).getByRole('button', { name: /Install x2/ }));
    expect(screen.getByRole('heading', { name: 'Install x2' })).toBeInTheDocument();
    const chips = screen.getByRole('group', { name: 'Show requests from' });
    await userEvent.click(within(chips).getByRole('button', { name: /System/ }));
    expect(within(screen.getByRole('list', { name: 'Waiting requests' })).getAllByRole('button')).toHaveLength(1);
    await userEvent.click(within(chips).getByRole('button', { name: /^All/ }));
    await userEvent.click(within(screen.getByRole('list', { name: 'Waiting requests' })).getByRole('button', { name: /Install x1/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onApprove).toHaveBeenCalledWith(expect.objectContaining({ id: 'x1' }));
    await noAxeViolations(container);
  });

  it('pauses decisions when the request list is stale', () => {
    render(<ApprovalsBoard actions={ready([a('x1', { id: 'agent:hermes', kind: 'agent' })], true)} plans={{}} now={NOW} canDecide={{ allowed: true }} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByText(/decisions are paused/)).toBeInTheDocument();
  });

  it('shows the empty state with the API query', () => {
    render(<ApprovalsBoard actions={ready([])} plans={{}} now={NOW} canDecide={{ allowed: true }} />);
    expect(screen.getByText('Nothing is waiting')).toBeInTheDocument();
    expect(screen.getByText('GET /v1/actions?state=awaiting_approval')).toBeInTheDocument();
  });
});

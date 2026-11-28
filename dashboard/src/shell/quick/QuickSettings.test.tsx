// SPDX-License-Identifier: Apache-2.0
// #841: the quick settings panel. Opens and closes by keyboard, quiet hours is one PUT with If-Match
// (a 409 re-reads), Stop all agents is the owner's alone and one call after the confirm, a failing
// tile says Unknown, the storage tile uses the measured free bytes, and axe finds nothing.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CustomizeProvider, LocalPreferencesStore } from '@onemind/ui';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';
import { seriousViolations } from '../../test/helpers';
import { QuickSettings } from './QuickSettings';
import { effectiveView, parseViewChoice } from './viewPref';
import { backupTile, formatBytes, networkTile, storageTile, updatesTile } from './quickData';

const json = (body: unknown, code = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status: code, headers: { 'content-type': 'application/json', ...headers } });

interface Gateway {
  quiet?: unknown;
  etag?: string;
  putStatus?: number;
  storage?: unknown;
  failing?: string[];
  killOn?: boolean;
}
function gateway(g: Gateway = {}) {
  let quiet: unknown = g.quiet ?? null;
  let etag = g.etag ?? '"e1"';
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (g.failing?.includes(path)) return json({ error: 'unavailable', message: 'no' }, 503);
    switch (path) {
      case '/v1/notifications/preferences':
        if (init?.method === 'PUT') {
          if (g.putStatus === 409) {
            etag = '"e2"';
            quiet = null;
            return json({ error: 'conflict', message: 'preferences changed since you read them (ETag mismatch)' }, 409);
          }
          quiet = (JSON.parse(String(init.body)) as { quiet_hours: unknown }).quiet_hours;
          etag = '"e3"';
        }
        return json({ quiet_hours: quiet, routes: [], digest: { enabled: false, at: '08:00' } }, 200, { etag });
      case '/v1/agents/kill-switch':
        if (init?.method === 'PUT') g.killOn = true;
        return json({ on: !!g.killOn, changed_by: null, changed_at: null, reason: null });
      case '/v1/network':
        return json({ available: true, interfaces: [{ name: 'eth0', state: 'up' }], gateways: [], dns: [], ports: [], dropped: 0 });
      case '/v1/os/updates':
        return json({ nodes: [{ node_id: 'n1', available_version: '1.2.0' }], install: {} });
      case '/v1/backups/status':
        return json({ health: 'ok', last_success_at: new Date(Date.now() - 3_600_000).toISOString() });
      case '/v1/storage':
        return json(g.storage ?? { node_id: 'n1', enabled: true, available: true, used_bytes: 10, available_bytes: 2_500_000_000_000 });
      default:
        return json({ error: 'not_found', message: path }, 404);
    }
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
const puts = (f: ReturnType<typeof gateway>, path: string) => f.mock.calls.filter(([u, i]) => new URL(String(u)).pathname === path && i?.method === 'PUT');

function mount(token: string, role: string | undefined, over: Partial<Parameters<typeof QuickSettings>[0]> = {}) {
  window.sessionStorage.setItem('onemind.token', token);
  const choice = vi.fn();
  const ui = render(
    <MemoryRouter>
      <SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}>
        <CustomizeProvider store={new LocalPreferencesStore({ storage: window.localStorage })}>
          <button type="button">outside</button>
          <QuickSettings role={role} view={role === 'owner' || role === 'adult' ? 'pro' : 'simple'} viewChoice="auto" onViewChoice={choice} {...over} />
        </CustomizeProvider>
      </SessionProvider>
    </MemoryRouter>,
  );
  return { ...ui, choice };
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); window.localStorage.clear(); });

const trigger = () => screen.getByRole('button', { name: 'Quick controls' });

describe('quick settings panel (#841)', () => {
  it('opens and closes with the keyboard and focus returns to the button', async () => {
    gateway();
    mount('owner-demo', 'owner');
    const u = userEvent.setup();
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    trigger().focus();
    await u.keyboard('{Enter}');
    expect(trigger()).toHaveAttribute('aria-expanded', 'true');
    const panel = screen.getByRole('region', { name: 'Quick settings' });
    expect(panel).toBeVisible();
    await u.keyboard('{Escape}');
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    expect(trigger()).toHaveFocus();
    await u.click(trigger());
    await u.click(screen.getByRole('button', { name: 'outside' }));
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
  });

  it('quiet hours sends one PUT with If-Match and the default night times', async () => {
    const f = gateway();
    mount('owner-demo', 'owner');
    const u = userEvent.setup();
    await u.click(trigger());
    const sw = await screen.findByRole('switch', { name: 'Quiet hours' });
    await waitFor(() => expect(sw).toBeEnabled());
    await u.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-checked', 'true'));
    const sent = puts(f, '/v1/notifications/preferences');
    expect(sent).toHaveLength(1);
    expect(new Headers(sent[0]![1]!.headers).get('if-match')).toBe('"e1"');
    const body = JSON.parse(String(sent[0]![1]!.body)) as { quiet_hours: { from: string; to: string; except_severity: string[]; except_topics: string[] } };
    expect(body.quiet_hours).toMatchObject({ from: '22:00', to: '07:00', except_severity: ['critical'], except_topics: ['approvals'] });
    expect(screen.getByText('On, 22:00 to 07:00')).toBeInTheDocument();
    // Off again clears it, and turning it on later brings the same times back.
    await u.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-checked', 'false'));
    expect((JSON.parse(String(puts(f, '/v1/notifications/preferences')[1]![1]!.body)) as { quiet_hours: unknown }).quiet_hours).toBeNull();
  });

  it('keeps the person’s saved quiet times when turning it on again', async () => {
    const saved = { tz: 'Europe/Berlin', from: '23:30', to: '06:15', except_severity: ['critical'], except_topics: ['approvals'] };
    const f = gateway({ quiet: saved });
    mount('owner-demo', 'owner');
    const u = userEvent.setup();
    await u.click(trigger());
    const sw = await screen.findByRole('switch', { name: 'Quiet hours' });
    await waitFor(() => expect(sw).toHaveAttribute('aria-checked', 'true'));
    await u.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-checked', 'false'));
    await u.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-checked', 'true'));
    expect((JSON.parse(String(puts(f, '/v1/notifications/preferences')[1]![1]!.body)) as { quiet_hours: unknown }).quiet_hours).toEqual(saved);
  });

  it('a 409 re-reads the preferences and says so', async () => {
    const f = gateway({ putStatus: 409 });
    mount('owner-demo', 'owner');
    const u = userEvent.setup();
    await u.click(trigger());
    const sw = await screen.findByRole('switch', { name: 'Quiet hours' });
    await waitFor(() => expect(sw).toBeEnabled());
    const gets = () => f.mock.calls.filter(([url, i]) => new URL(String(url)).pathname === '/v1/notifications/preferences' && (i?.method ?? 'GET') === 'GET').length;
    const before = gets();
    await u.click(sw);
    expect(await screen.findByText(/changed somewhere else/)).toBeInTheDocument();
    expect(gets()).toBe(before + 1);
    expect(sw).toHaveAttribute('aria-checked', 'false');
  });

  it('shows Stop all agents to the owner only and sends the kill switch once after the confirm', async () => {
    const f = gateway();
    mount('owner-demo', 'owner');
    const u = userEvent.setup();
    await u.click(trigger());
    await u.click(await screen.findByRole('button', { name: 'Stop all agents' }));
    expect(puts(f, '/v1/agents/kill-switch')).toHaveLength(0); // nothing before the confirm
    const dlg = await screen.findByRole('alertdialog');
    expect(trigger()).toHaveAttribute('aria-expanded', 'true'); // the dialog, not the panel, took the click
    await u.click(within(dlg).getByRole('button', { name: 'Stop agents' }));
    await waitFor(() => expect(puts(f, '/v1/agents/kill-switch')).toHaveLength(1));
    expect(JSON.parse(String(puts(f, '/v1/agents/kill-switch')[0]![1]!.body))).toEqual({ on: true });
    expect(await screen.findByText(/Agent requests are blocked at the hub/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /resume/i })).toBeNull(); // resuming lives in Agents
    expect(screen.getByRole('link', { name: /Open Agents/ })).toHaveAttribute('href', '/settings/agents');
  });

  it('hides Stop all agents and the box tiles from other roles', async () => {
    const f = gateway();
    mount('adult-demo', 'adult');
    const u = userEvent.setup();
    await u.click(trigger());
    await screen.findByRole('switch', { name: 'Quiet hours' });
    expect(screen.queryByRole('button', { name: 'Stop all agents' })).toBeNull();
    expect(await screen.findByText('Last backup')).toBeInTheDocument();
    expect(screen.queryByText('Network')).toBeNull(); // GET /v1/network is owner only
    expect(f.mock.calls.some(([url]) => new URL(String(url)).pathname === '/v1/agents/kill-switch')).toBe(false);
  });

  it('a failing tile route says Unknown, never a green state, and null free space is Unknown', async () => {
    gateway({ failing: ['/v1/os/updates', '/v1/backups/status'], storage: { node_id: 'n1', enabled: true, available: true, used_bytes: 5, available_bytes: null } });
    mount('owner-demo', 'owner');
    await userEvent.setup().click(trigger());
    for (const label of ['Updates', 'Last backup', 'Storage']) {
      const tile = (await screen.findByText(label)).closest('a')!;
      await waitFor(() => expect(within(tile).getByText('Unknown')).toBeInTheDocument());
      expect(tile.className).toContain('qs-tone-unknown');
    }
    const net = (await screen.findByText('Network')).closest('a')!;
    await waitFor(() => expect(within(net).getByText('Connected')).toBeInTheDocument());
  });

  it('the storage tile shows the measured free bytes and opens Storage', async () => {
    gateway();
    mount('owner-demo', 'owner');
    await userEvent.setup().click(trigger());
    const tile = (await screen.findByText('Storage')).closest('a')!;
    await waitFor(() => expect(within(tile).getByText('2.5 TB free')).toBeInTheDocument());
    expect(tile).toHaveAttribute('href', '/storage');
  });

  it('theme buttons use the customize provider', async () => {
    gateway();
    mount('owner-demo', 'owner');
    const u = userEvent.setup();
    await u.click(trigger());
    await u.click(screen.getByRole('button', { name: 'Dark' }));
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
    await u.click(screen.getByRole('button', { name: 'Light' }));
    expect(screen.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('Simple or Pro follows the role: a Pro role may narrow to Simple, a Simple role cannot pick Pro', async () => {
    gateway();
    const a = mount('owner-demo', 'owner');
    const u = userEvent.setup();
    await u.click(trigger());
    await u.click(screen.getByRole('button', { name: 'Simple' }));
    expect(a.choice).toHaveBeenCalledWith('simple');
    a.unmount();
    const b = mount('child-demo', 'child');
    await u.click(trigger());
    expect(screen.getByRole('button', { name: 'Pro' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Simple' })).toBeDisabled();
    expect(b.choice).not.toHaveBeenCalled();
    expect(effectiveView('simple', 'auto')).toBe('simple');
    expect(effectiveView('pro', 'simple')).toBe('simple');
    expect(effectiveView('pro', 'auto')).toBe('pro');
    expect(effectiveView('unknown', 'simple')).toBe('unknown');
    expect(parseViewChoice('pro')).toBe('auto');
  });

  it('has no serious axe violations, open or closed', async () => {
    gateway();
    const { container } = mount('owner-demo', 'owner');
    expect(await seriousViolations(container)).toEqual([]);
    await userEvent.setup().click(trigger());
    await screen.findByRole('switch', { name: 'Quiet hours' });
    await act(async () => { fireEvent.focus(trigger()); });
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe('tile mapping (#841)', () => {
  it('maps each answer without inventing a value', () => {
    expect(storageTile({ enabled: true, available: true, available_bytes: 1_500_000_000 }).value).toBe('1.5 GB free');
    expect(storageTile({ enabled: true, available: true, available_bytes: null }).value).toBe('Unknown');
    expect(storageTile({ enabled: true, available: false }).tone).toBe('unknown');
    expect(storageTile('x').tone).toBe('unknown');
    expect(networkTile({ available: false, interfaces: [] }).tone).toBe('unknown');
    expect(networkTile({ available: true, interfaces: [{ state: 'down' }] }).tone).toBe('bad');
    expect(updatesTile({ nodes: [{ available_version: null }] }).value).toBe('Up to date');
    expect(updatesTile({}).tone).toBe('unknown');
    expect(backupTile({ health: 'failing' }, 0).tone).toBe('bad');
    expect(backupTile({ health: 'not_configured' }, 0).value).toBe('Not set up');
    expect(backupTile({ health: 'ok', last_success_at: '2026-11-20T00:00:00Z' }, Date.parse('2026-11-22T01:00:00Z')).value).toBe('2 days ago');
    expect(formatBytes(999)).toBe('999 B');
  });
});

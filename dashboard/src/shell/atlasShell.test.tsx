// SPDX-License-Identifier: Apache-2.0
// The Atlas shell (#1017, #844, #501; final design 01, 03, 09): the dock in the design's order with the logo tile
// first, the status strip from real answers, the launcher with the exact onemind command for each action, and the
// run bar (off by default) that never drops a dock item silently and never files a request twice.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { NavItem, PaletteCommand } from '@onemind/ui';
import { renderApp } from '../test/helpers';
import { DockApps } from './DockApps';
import { MAP_PATH, dockOrder, dockSplit, makeRoomForRunBar } from './dock';
import { commandLine, launcherItems, searchLauncher } from './launcher';
import { resolveRun } from './RunBar';
import { NeedsYouChip, fleetCounts, fleetSentence, needsYouLabel } from './StatusStrip';

const T = { timeout: 4000 };
const item = (id: string): NavItem => ({ id, label: id[0]!.toUpperCase() + id.slice(1), href: `/${id}`, icon: 'home' });

const RESTART: PaletteCommand = { id: 'req:restart:nextcloud', group: 'Requests', title: 'Request restart of Nextcloud', keywords: ['restart', 'nextcloud'], icon: 'updates', request: { type: 'app.restart', params: { app_id: 'nextcloud' } }, equivalent: 'POST /v1/actions {"type":"app.restart","params":{"app_id":"nextcloud"}}' };
const INSTALL: PaletteCommand = { id: 'req:install:immich', group: 'Requests', title: 'Request install of Immich', keywords: ['install', 'immich'], icon: 'apps', request: { type: 'app.install', params: { app_id: 'immich' } }, equivalent: 'onemind apps install immich --no-approve' };
const OPEN: PaletteCommand = { id: 'go:nodes', group: 'Go to', title: 'Nodes', icon: 'nodes', href: '#/nodes' };
const APPROVAL: PaletteCommand = { id: 'approval:a1', group: 'Approvals', title: 'Review: Restart Nextcloud', icon: 'approvals', href: '#/approvals/a1', equivalent: 'onemind actions info a1' };

describe('dock order (final design 01)', () => {
  it('puts Map second, linked to /map, until the Map screen registers itself', () => {
    expect(dockOrder(['home', 'approvals', 'files'], false)).toEqual(['home', 'map', 'approvals', 'files']);
    expect(dockOrder(['home', 'map', 'approvals'], true)).toEqual(['home', 'map', 'approvals']);
    const { dock } = dockSplit([item('files'), item('home')], ['home', 'map', 'files'], false);
    expect(dock.map((n) => [n.id, n.href])).toEqual([['home', '/home'], ['map', MAP_PATH], ['files', '/files']]);
  });

  it('once a map screen exists, its own nav item and role gate win: no placeholder for someone it is hidden from', () => {
    expect(dockSplit([item('home')], ['home', 'map'], true).dock.map((n) => n.id)).toEqual(['home']);
    expect(dockSplit([item('home'), { ...item('map'), label: 'Map', badge: 2 }], ['home', 'map'], true).dock[1]).toMatchObject({ label: 'Map', badge: 2 });
  });

  it('the registry order is the Atlas default: Home, Map, Approvals, Files, Market, Backups (Protect), Machines', () => {
    expect(dockOrder()).toEqual(['home', 'map', 'approvals', 'files', 'market', 'backups', 'machines']);
  });
});

describe('the run bar never drops a dock item silently', () => {
  const apps = ['Immich', 'Vaultwarden', 'Jellyfin', 'Frigate'].map((name) => ({ id: name.toLowerCase(), name, href: `/apps/${name.toLowerCase()}` }));

  it('keeps every app when the run bar is off, and moves the rest into More when it is on', () => {
    expect(makeRoomForRunBar(apps, false)).toEqual({ shown: apps, moved: [] });
    const { shown, moved } = makeRoomForRunBar(apps, true);
    expect(shown.map((a) => a.name)).toEqual(['Immich', 'Vaultwarden']);
    expect(moved.map((a) => a.name)).toEqual(['Jellyfin', 'Frigate']);
  });

  it('More names the moved apps and opens the launcher', () => {
    const onMore = vi.fn();
    const { rerender } = render(<DockApps apps={apps} runBar={false} onMore={onMore} />);
    expect(screen.getAllByRole('link')).toHaveLength(4);
    expect(screen.queryByRole('button', { name: /More/ })).toBeNull();
    rerender(<DockApps apps={apps} runBar onMore={onMore} />);
    expect(screen.getAllByRole('link')).toHaveLength(2);
    const more = screen.getByRole('button', { name: /More/ });
    expect(more).toHaveAccessibleName('More: Jellyfin, Frigate (moved to make room for the run bar)');
    fireEvent.click(more);
    expect(onMore).toHaveBeenCalledTimes(1);
  });
});

describe('run bar resolution (#844, final design 09)', () => {
  const all = [RESTART, INSTALL, OPEN, APPROVAL];

  it('resolves "restart nextcloud" to the app.restart request, which goes through the reviewed request path', () => {
    const r = resolveRun('restart nextcloud', all, []);
    expect(r).toEqual({ kind: 'run', command: RESTART });
  });

  it('opens the request already waiting instead of filing a second one', () => {
    const r = resolveRun('restart nextcloud', all, [{ id: 'a1', type: 'app.restart', appId: 'nextcloud' }]);
    expect(r).toEqual({ kind: 'existing', href: '/approvals/a1', command: RESTART });
    // A different app's request does not count.
    expect(resolveRun('restart nextcloud', all, [{ id: 'a2', type: 'app.restart', appId: 'immich' }]).kind).toBe('run');
  });

  it('opens a screen, ignores blocked commands and says so when nothing matches', () => {
    expect(resolveRun('nodes', all, [])).toEqual({ kind: 'run', command: OPEN });
    expect(resolveRun('restart nextcloud', [{ ...RESTART, disabledReason: 'Only the owner can request a restart.' }], []).kind).toBe('none');
    expect(resolveRun('what is the weather', all, []).kind).toBe('none');
    expect(resolveRun('   ', all, []).kind).toBe('none');
  });
});

describe('launcher logic (final design 03)', () => {
  const data = {
    nav: [item('home'), item('approvals'), item('files')],
    apps: [{ id: 'immich', name: 'Immich', href: '/apps/immich' }],
    machines: [{ id: 'n1', name: 'garage-pi', status: 'stale' as const }],
    commands: [RESTART, INSTALL, OPEN, APPROVAL],
  };

  it('shows the exact onemind command where the CLI has one, else the API call', () => {
    expect(commandLine(INSTALL)).toEqual({ cli: true, text: '$ onemind apps install immich --no-approve' });
    expect(commandLine(RESTART)).toEqual({ cli: false, text: RESTART.equivalent });
    expect(commandLine(OPEN)).toBeUndefined();
  });

  it('counts each kind, lists only commands that act or have a line, and ranks a best match', () => {
    const items = launcherItems(data);
    const r = searchLauncher(items, '', 'all');
    expect(r.counts).toEqual({ apps: 1, system: 3, machines: 1, commands: 3 });
    expect(r.best).toEqual([]);
    const typed = searchLauncher(items, 'garage', 'all');
    expect(typed.best[0]?.title).toBe('garage-pi');
    expect(searchLauncher(items, 'immich', 'commands').best.map((i) => i.key)).toEqual(['cmd:req:install:immich']);
  });
});

describe('status strip', () => {
  it('counts machines with Atlas words and says it in one sentence', () => {
    const c = fleetCounts(['online', 'online', 'stale', 'offline']);
    expect(c).toEqual({ fresh: 2, stale: 1, offline: 1 });
    expect(fleetSentence(c)).toBe('4 machines: 2 fresh, 1 stale, 1 offline');
    expect(fleetSentence(fleetCounts(['online']))).toBe('1 machine: 1 fresh, 0 stale, 0 offline');
  });

  it('the needs-you chip opens Approvals and reads calmly when nothing waits', () => {
    expect(needsYouLabel(0)).toBe('Nothing needs you');
    expect(needsYouLabel(1)).toBe('1 needs you');
    expect(needsYouLabel(3)).toBe('3 need you');
    render(<NeedsYouChip waiting={2} />);
    expect(screen.getByRole('link', { name: '2 need you' })).toHaveAttribute('href', '/approvals');
  });
});

describe('the desktop shell, wired to the hub', () => {
  it('starts the dock with the OneMind logo tile, then the Atlas places', async () => {
    renderApp({ token: 'owner-demo' });
    const dock = await screen.findByRole('navigation', { name: 'Main' }, T);
    const first = dock.querySelector('.dsk-dock-item');
    expect(first).toHaveAccessibleName(/^OneMind launcher/);
    await within(dock).findByRole('link', { name: /Machines/ }, T); // Pro places appear once the role is known
    const places = [...dock.querySelectorAll('a.dsk-dock-item .dsk-dock-label')].map((l) => l.textContent);
    expect(places.slice(0, 7)).toEqual(['Home', 'Map', 'Approvals', 'Files', 'Market', 'Backups', 'Machines']);
    expect(within(dock).getByRole('link', { name: 'Map' })).toHaveAttribute('href', MAP_PATH);
    // The old bright per-screen colours are gone: tiles carry no inline hue.
    expect(dock.querySelector('.dsk-tile[style*="--dsk-tile-a"]')).toBeNull();
  });

  it('shows fresh/stale/offline counts from GET /v1/nodes and the needs-you chip from the waiting requests', async () => {
    const { container, getApi } = renderApp({ token: 'owner-demo' });
    const nodes = await getApi().nodes();
    await waitFor(() => expect(container.querySelector('.dsk-fleet')).not.toBeNull(), T);
    const sentence = container.querySelector('.dsk-fleet .om-visually-hidden')?.textContent ?? '';
    expect(sentence).toMatch(new RegExp(`^${nodes.length} machines: \\d+ fresh, \\d+ stale, \\d+ offline$`));
    const waiting = (await getApi().actions()).filter((a) => a.state === 'awaiting_approval').length;
    expect(await screen.findByRole('link', { name: needsYouLabel(waiting) }, T)).toHaveAttribute('href', '/approvals');
  });

  it('the launcher lists commands with their exact onemind line and marks requests "asks a person"', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo' });
    await u.click(await screen.findByRole('button', { name: /OneMind launcher/ }, T));
    const lp = within(await screen.findByRole('dialog', { name: 'Launcher' }));
    const commands = lp.getByRole('region', { name: 'Commands' });
    expect(within(commands).getAllByText(/^\$ onemind /).length).toBeGreaterThan(0);
    await u.type(lp.getByRole('searchbox'), 'install');
    const best = lp.getByRole('region', { name: 'Best match' });
    expect(within(best).getAllByText('asks a person').length).toBeGreaterThan(0);
  });

  it('a launcher request opens the review first and posts nothing to /v1/actions before Send request (D-027)', async () => {
    const u = userEvent.setup();
    const { getApi } = renderApp({ token: 'owner-demo' });
    const create = vi.spyOn(getApi(), 'createAction');
    await u.click(await screen.findByRole('button', { name: /OneMind launcher/ }, T));
    const lp = within(await screen.findByRole('dialog', { name: 'Launcher' }));
    await u.type(lp.getByRole('searchbox'), 'install');
    await u.click(lp.getAllByRole('button', { name: /^Request install of/ })[0]!);
    const review = await screen.findByRole('dialog', { name: 'Review app request' }, T);
    expect(create).not.toHaveBeenCalled();
    await u.click(within(review).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1), T);
    expect(create.mock.calls[0]![0]).toMatchObject({ type: 'app.install' });
  });

  it('copying a command line is announced, then the announcement clears', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      // user-event installs its own clipboard on setup: watch that one.
      const writeText = vi.spyOn(navigator.clipboard, 'writeText');
      renderApp({ token: 'owner-demo' });
      await u.click(await screen.findByRole('button', { name: /OneMind launcher/ }, T));
      const lp = within(await screen.findByRole('dialog', { name: 'Launcher' }));
      await u.click(lp.getAllByRole('button', { name: /^Copy command/ })[0]!);
      expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^onemind /));
      const status = lp.getByRole('status');
      await waitFor(() => expect(status).toHaveTextContent(/^Copied: onemind /));
      await vi.advanceTimersByTimeAsync(2500);
      expect(status).toHaveTextContent('');
    } finally {
      vi.useRealTimers();
    }
  });
});

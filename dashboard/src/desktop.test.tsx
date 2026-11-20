// SPDX-License-Identifier: Apache-2.0
// D-016: the Desktop frame is the default. "/" is the wallpaper desktop with a dock; every other
// screen opens as a window over it (close button, Esc); the Console (sidebar) stays one click away
// and is remembered per person.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { NavItem } from '@onemind/ui';
import { dockGroups } from './shell/DesktopShell';
import { layoutModeStore, parseLayoutMode } from './shell/layoutMode';
import { renderApp, seriousViolations } from './test/helpers';

const T = { timeout: 4000 };

/** A Storage stand-in: Node 25+ has no jsdom localStorage in tests (src/test/setup.ts). */
function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: (k) => void m.delete(k), clear: () => m.clear(), key: () => null, get length() { return m.size; } } as Storage;
}
const hasLocalStorage = typeof window !== 'undefined' && !!window.localStorage;

describe('layout mode', () => {
  it('defaults to desktop and only accepts the two known values', () => {
    expect(parseLayoutMode(null)).toBe('desktop');
    expect(parseLayoutMode('console')).toBe('console');
    expect(parseLayoutMode('sidebar')).toBe('desktop');
  });

  it('is stored per person', () => {
    const base = memoryStorage();
    layoutModeStore('owner', base).save('console');
    expect(layoutModeStore('owner', base).load()).toBe('console');
    expect(layoutModeStore('alex', base).load()).toBe('desktop');
    expect(layoutModeStore('owner', null).load()).toBe('desktop'); // no storage: the default
  });

  it('groups the dock: primary items first, then the sidebar groups in order', () => {
    const item = (id: string, extra: Partial<NavItem> = {}): NavItem => ({ id, label: id, href: `/${id}`, icon: 'home', ...extra });
    const groups = dockGroups([item('sys', { group: 'System' }), item('home', { primary: true }), item('box', { group: 'Your box' }), item('market', { primary: true })]);
    expect(groups.map((g) => g.map((n) => n.id))).toEqual([['home', 'market'], ['box'], ['sys']]);
  });
});

describe('desktop frame', () => {
  it('shows the desktop at "/" with the dock and no window', async () => {
    const { container } = renderApp({ token: 'owner-demo' });
    const dock = within(await screen.findByRole('navigation', { name: 'Main' }, T));
    expect(dock.getByRole('link', { name: /Home/ })).toHaveAttribute('aria-current', 'page');
    expect(dock.getByRole('link', { name: /Market/ })).toBeInTheDocument();
    expect(container.querySelector('.dsk-at-home')).not.toBeNull();
    expect(container.querySelector('.dsk-window')).toBeNull();
    expect(container.querySelector('.om-shell')).toBeNull(); // no sidebar
  });

  it('opens a screen as a window over the wallpaper, closes it with ✕ and with Esc, and passes axe', async () => {
    const u = userEvent.setup();
    const { container } = renderApp({ token: 'owner-demo', route: '/market' });
    const win = await screen.findByRole('region', { name: 'Market' }, T);
    expect(within(win).getByRole('main')).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);

    await u.click(within(win).getByRole('link', { name: 'Close Market' }));
    await waitFor(() => expect(container.querySelector('.dsk-at-home')).not.toBeNull());

    const dock = within(screen.getByRole('navigation', { name: 'Main' }));
    await u.click(dock.getByRole('link', { name: /Activity/ }));
    expect(await screen.findByRole('region', { name: 'Activity' }, T)).toBeInTheDocument();
    await u.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Activity' })).toBeNull());
  });

  it.skipIf(!hasLocalStorage)('switches to the Console sidebar and back, and remembers the choice', async () => {
    const u = userEvent.setup();
    const { container, unmount } = renderApp({ token: 'owner-demo' });
    await u.click(await screen.findByRole('button', { name: 'Console view' }, T));
    await waitFor(() => expect(container.querySelector('.om-shell')).not.toBeNull());
    expect(container.querySelector('.dsk')).toBeNull();
    unmount();

    const again = renderApp({ token: 'owner-demo' });
    await screen.findByRole('button', { name: 'Desktop view' }, T);
    expect(again.container.querySelector('.om-shell')).not.toBeNull();
  });

  it('keeps Pro screens out of the dock for a guest', async () => {
    renderApp({ token: 'guest-demo' });
    const dock = within(await screen.findByRole('navigation', { name: 'Main' }, T));
    expect(dock.getByRole('link', { name: /Home/ })).toBeInTheDocument();
    expect(dock.queryByRole('link', { name: /Nodes/ })).toBeNull();
  });
});

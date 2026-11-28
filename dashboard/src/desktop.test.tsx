// SPDX-License-Identifier: Apache-2.0
// D-016: the Desktop frame is the default. "/" is the wallpaper desktop with a dock; every other
// screen opens as a window over it (close button, Esc); the Console (sidebar) stays one click away
// and is remembered per person.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { NavItem } from '@onemind/ui';
import { avatarInitial, dockSplit, parentPath } from './shell/DesktopShell';
import { dockOrder } from './shell/dock';
import { layoutModeStore, parseLayoutMode } from './shell/layoutMode';
import { openScreen, renderApp, screensNav, seriousViolations } from './test/helpers';

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

  it('splits the nav: the Atlas places in the dock (Map second, at /map), the rest in the launcher', () => {
    const item = (id: string, extra: Partial<NavItem> = {}): NavItem => ({ id, label: id, href: `/${id}`, icon: 'home', ...extra });
    const nav = [item('nodes', { group: 'Your box' }), item('settings'), item('files'), item('home', { primary: true }), item('market', { primary: true })];
    const atlas = ['home', 'approvals', 'files', 'market', 'backups', 'machines'];
    // Explicit order and map flag, so this holds both before and after the Map screen (#1340) registers itself.
    const before = dockSplit(nav, dockOrder(atlas, false), false);
    expect(before.dock.map((n) => n.id)).toEqual(['home', 'map', 'files', 'market']);
    expect(before.dock[1]?.href).toBe('/map');
    expect(before.more.map((n) => n.id)).toEqual(['nodes', 'settings']);
    const after = dockSplit([...nav, item('map')], dockOrder(['home', 'map', ...atlas.slice(1)], true), true);
    expect(after.dock.map((n) => n.id)).toEqual(['home', 'map', 'files', 'market']);
    expect(after.more.map((n) => n.id)).toEqual(['nodes', 'settings']);
  });

  it('knows the way back up inside a screen', () => {
    expect(parentPath('/market/vaultwarden')).toBe('/market');
    expect(parentPath('/market')).toBeNull();
    expect(parentPath('/')).toBeNull();
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
    expect(screen.getByRole('main')).toContainElement(win);
    expect(await seriousViolations(container)).toEqual([]);

    await u.click(within(win).getByRole('button', { name: 'Close Market' }));
    await waitFor(() => expect(container.querySelector('.dsk-at-home')).not.toBeNull());

    await openScreen(u, /Activity/); // in the launcher: the Atlas dock has no Activity tile
    expect(await screen.findByRole('region', { name: 'Activity' }, T)).toBeInTheDocument();
    await u.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Activity' })).toBeNull());
  });

  it('says the screen name once to assistive tech, while the Atlas title bar shows it to the eye', async () => {
    const { container } = renderApp({ token: 'owner-demo', route: '/market' });
    const win = await screen.findByRole('region', { name: 'Market' }, T);
    // The region is named once, by its visually hidden label; the title bar's name is hidden from assistive tech.
    expect(container.querySelector('.dsk-window > .om-visually-hidden')?.textContent).toBe('Market');
    const bar = win.querySelector('.wm-title');
    expect(bar?.textContent).toBe('Market');
    expect(bar).toHaveAttribute('aria-hidden', 'true');
    expect(within(win).getByRole('button', { name: 'Close Market' })).toBeInTheDocument();
  });

  it('Home greets without the role word and names apps as the catalog does', async () => {
    renderApp({ token: 'owner-demo' });
    const h1 = await screen.findByRole('heading', { level: 1 }, T);
    expect(h1.textContent).toMatch(/^Good (morning|afternoon|evening|night)$/);
    expect(await screen.findByText('Install Ollama', {}, T)).toBeInTheDocument();
    expect(screen.queryByText('Install ollama')).toBeNull();
    // The raw activity log is in the Activity window, not on the default Home.
    expect(screen.queryByRole('region', { name: 'Recent activity' })).toBeNull();
    expect(screen.getByRole('region', { name: 'Backups' })).toHaveTextContent('No backup proved yet');
  });

  it('marks mock screens with a Demo data badge in the menu bar', async () => {
    const { container } = renderApp({ token: 'owner-demo' });
    await screen.findByRole('navigation', { name: 'Main' }, T);
    expect(container.querySelector('.dsk-bar .dsk-demo')).toHaveTextContent('Demo data');
  });

  it('the launcher lists your apps first, larger, and the system screens after in a smaller row', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo' });
    await u.click(await screen.findByRole('button', { name: /screens and apps/ }, T));
    const lp = await screen.findByRole('dialog', { name: 'Launcher' });
    const sections = [...lp.querySelectorAll('section')].map((s) => s.getAttribute('aria-label'));
    expect(sections[0]).toBe('Your apps');
    expect(sections).toContain('System');
    expect(lp.querySelector('.dsk-launchpad-big')).not.toBeNull();
    expect(lp.querySelector('.dsk-launchpad-small')).not.toBeNull();
  });

  it.skipIf(!hasLocalStorage)('switches to the Console sidebar and back, and remembers the choice', async () => {
    const u = userEvent.setup();
    const { container, unmount } = renderApp({ token: 'owner-demo' });
    await u.click(await screen.findByRole('button', { name: /Account/ }, T));
    await u.click(screen.getByRole('button', { name: 'Console view' }));
    await waitFor(() => expect(container.querySelector('.om-shell')).not.toBeNull());
    expect(container.querySelector('.dsk')).toBeNull();
    unmount();

    const again = renderApp({ token: 'owner-demo' });
    await screen.findByRole('button', { name: 'Desktop view' }, T);
    expect(again.container.querySelector('.om-shell')).not.toBeNull();
  });

  it('keeps Pro screens out of the dock and the launcher for a guest', async () => {
    renderApp({ token: 'guest-demo' });
    const dock = within(await screen.findByRole('navigation', { name: 'Main' }, T));
    expect(dock.getByRole('link', { name: /Home/ })).toBeInTheDocument();
    const lp = await screensNav(userEvent.setup());
    expect(lp.getByRole('link', { name: /Activity/ })).toBeInTheDocument();
    expect(lp.queryByRole('link', { name: /Nodes/ })).toBeNull();
  });

  it('the launcher lists every screen, filters as you type, and closes with Esc', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo' });
    const lp = await screensNav(u);
    expect(lp.getByRole('link', { name: /Control Hub/ })).toBeInTheDocument();
    await u.type(lp.getByRole('searchbox', { name: 'Find an app, screen, machine or command' }), 'back');
    expect(lp.getByRole('link', { name: /Backups/ })).toBeInTheDocument();
    expect(lp.queryByRole('link', { name: /Control Hub/ })).toBeNull();
    await u.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Launcher' })).toBeNull());
  });

  it('Esc closes the bell popover or leaves a search field without closing the window', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo', route: '/market' });
    await screen.findByRole('region', { name: 'Market' }, T);
    await u.click(screen.getByRole('button', { name: /^Notifications/ }));
    await u.keyboard('{Escape}');
    expect(screen.getByRole('region', { name: 'Market' })).toBeInTheDocument();
    await u.click(screen.getByPlaceholderText(/Search apps/));
    await u.keyboard('{Escape}');
    expect(screen.getByRole('region', { name: 'Market' })).toBeInTheDocument();
  });

  it('the launcher hands focus back to the logo tile when it closes', async () => {
    const u = userEvent.setup();
    renderApp({ token: 'owner-demo' });
    const nav = within(await screen.findByRole('navigation', { name: 'Main' }, T));
    const all = nav.getByRole('button', { name: /screens and apps/ });
    await u.click(all);
    const lp = within(await screen.findByRole('dialog', { name: 'Launcher' }));
    expect(lp.getByRole('searchbox')).toHaveFocus();
    await u.keyboard('{Escape}');
    await waitFor(() => expect(all).toHaveFocus());
  });

  it('a nested page has a Back button to its screen', async () => {
    renderApp({ token: 'owner-demo', route: '/market/vaultwarden' });
    const win = await screen.findByRole('region', { name: 'Market' }, T);
    await userEvent.click(within(win).getByRole('button', { name: 'Back' }));
    expect(await within(win).findByPlaceholderText(/Search apps/)).toBeInTheDocument();
  });
});

describe('avatar initial', () => {
  it('uses the greeted name first, then the account id, then a question mark', () => {
    expect(avatarInitial('alex', undefined)).toBe('A');
    expect(avatarInitial('Zeus', 'owner')).toBe('Z');
    expect(avatarInitial(undefined, 'pi')).toBe('P');
    expect(avatarInitial('  ', undefined)).toBe('?');
    expect(avatarInitial()).toBe('?');
  });
});

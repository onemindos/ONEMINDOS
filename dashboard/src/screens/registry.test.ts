// SPDX-License-Identifier: Apache-2.0
import { SETTINGS_SECTIONS } from '@onemind/ui';
import { DOCK_ORDER, PRO_SCREEN_IDS, SCREENS, SCREEN_FILES, SETTINGS_FILES, SETTINGS_PAGES, navIdFor, navItems, screenProblems } from './registry';
import type { ScreenDef } from './types';

const ok: ScreenDef = { id: 'a', path: '/a', title: 'A', icon: 'home', section: 'Your box', order: 1, hue: ['#000', '#fff'], load: async () => ({ default: () => null }) };

describe('screen registry', () => {
  it('every screen file on disk is sound: required fields, one id and one path each', () => {
    expect(Object.keys(SCREEN_FILES).length).toBeGreaterThanOrEqual(15);
    expect(screenProblems(SCREEN_FILES)).toEqual([]);
  });

  it('fails a screen with a missing field', () => {
    const noHue: Partial<ScreenDef> = { ...ok, hue: undefined };
    expect(screenProblems({ './a/screen.ts': noHue as ScreenDef })).toEqual(['./a/screen.ts: missing "hue"']);
  });

  it('fails two screens that claim one path or one id, or a folder that differs from the id', () => {
    const p = screenProblems({ './a/screen.ts': ok, './b/screen.ts': { ...ok, id: 'b' }, './c/screen.ts': { ...ok, id: 'c', path: '/x', extra: [{ path: '/a' }] } });
    expect(p).toEqual(expect.arrayContaining([expect.stringContaining('path "a" is claimed by both ./a/screen.ts and ./b/screen.ts')]));
    expect(p.some((m) => m.includes('path "a" is claimed by both ./a/screen.ts and ./c/screen.ts'))).toBe(true);
    expect(screenProblems({ './a/screen.ts': ok, './b/screen.ts': ok }).some((m) => m.includes('id "a" is claimed'))).toBe(true);
    expect(screenProblems({ './zzz/screen.ts': ok })).toEqual(['./zzz/screen.ts: id "a" must match the folder name']);
  });

  it('a hidden screen is routed and windowed but never offered in the sidebar or Launchpad', () => {
    const app = SCREENS.find((s) => s.id === 'app');
    expect(app).toMatchObject({ path: '/apps/:appId', hidden: true });
    expect(navItems(0).some((n) => n.id === 'app')).toBe(false);
    expect(navIdFor('/apps/uptime-kuma')).toBe('app');
  });

  it('keeps the nav order, groups, Pro set and dock the shell had before the registry', () => {
    const expected = [
      ['home', '/', 'primary'],
      ['market', '/market', 'primary'],
      ['approvals', '/approvals', 'primary'],
      ['activity', '/activity', 'primary'],
      ['files', '/files', 'Your box'],
      ['search', '/search', 'Your box'],
      ['installed', '/installed', 'Your box'],
      ['nodes', '/nodes', 'Your box'],
      ['add-machine', '/add-machine', 'Your box'],
      ['world', '/world', 'Your box'],
      ['machines', '/machines', 'Your box'],
      ['photos', '/photos', 'Your box'],
      ['alerts', '/alerts', 'Your box'],
      ['usage', '/usage', 'Your box'],
      ['dashboards', '/dashboards', 'Your box'],
      ['storage', '/storage', 'Your box'],
      ['backups', '/backups', 'Your box'],
      ['file-sharing', '/file-sharing', 'Your box'],
      ['troubleshoot', '/troubleshoot', 'Your box'],
      ['tips', '/tips', 'Your box'],
      ['network', '/network', 'Your box'],
      ['automation', '/automation', 'Your box'],
      ['updates', '/updates', 'Your box'],
      ['settings', '/settings', 'Your box'],
      ['migrate', '/migrate', 'System'],
      ['control-hub', '/control-hub', 'System'],
      ['agents', '/agents', 'System'],
      ['plugins', '/plugins', 'System'],
    ];
    expected.splice(expected.findIndex(([id]) => id === 'storage'), 0, ['work', '/work', 'Your box']);
    expect(navItems(2).map((n) => [n.id, n.href, n.group ?? 'primary'])).toEqual(expected);
    expect(navItems(2).find((n) => n.id === 'approvals')).toMatchObject({ badge: 2, badgeLabel: '2 waiting' });
    expect([...PRO_SCREEN_IDS].sort()).toEqual(['add-machine', 'agents', 'automation', 'backups', 'control-hub', 'dashboards', 'file-sharing', 'machines', 'migrate', 'network', 'nodes', 'photos', 'plugins', 'storage', 'troubleshoot', 'updates', 'usage', 'world']);
    expect(DOCK_ORDER).toEqual(['home', 'market', 'installed', 'approvals', 'activity', 'settings']);
    expect(SCREENS.every((s) => s.title.length > 0)).toBe(true);
  });

  it('maps detail pages and tabs to their screen', () => {
    expect(navIdFor('/')).toBe('home');
    expect(navIdFor('/market/x')).toBe('market');
    expect(navIdFor('/sources')).toBe('market');
    expect(navIdFor('/compose')).toBe('market');
    expect(navIdFor('/installed/x')).toBe('installed');
    expect(navIdFor('/settings/users')).toBe('settings');
    expect(navIdFor('/tips/find-an-app')).toBe('tips');
    expect(navIdFor('/nowhere')).toBe('nowhere');
  });
});

describe('settings registry', () => {
  it('has exactly one page for each @onemind/ui settings section, each with a page, a link to its own screen or a coming note', () => {
    expect(Object.values(SETTINGS_FILES).length).toBe(SETTINGS_PAGES.size);
    expect([...SETTINGS_PAGES.keys()].sort()).toEqual(SETTINGS_SECTIONS.map((s) => s.id).sort());
    for (const p of SETTINGS_PAGES.values()) expect([p.load, p.to, p.coming].filter(Boolean)).toHaveLength(1);
  });

  it('links each section that has its own screen to the path that screen redirects from /settings/<id>', () => {
    const linked = [...SETTINGS_PAGES.values()].filter((p) => p.to);
    expect(linked.map((p) => p.id).sort()).toEqual(['automation', 'backups', 'devices', 'network', 'storage', 'updates']);
    for (const p of linked) {
      const screen = SCREENS.find((s) => s.path === p.to);
      expect(screen, `${p.id} links to ${p.to}`).toBeDefined();
      expect(screen!.redirects ?? []).toContainEqual({ from: `/settings/${p.id}`, to: p.to });
    }
  });
});

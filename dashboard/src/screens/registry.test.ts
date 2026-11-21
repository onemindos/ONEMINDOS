// SPDX-License-Identifier: Apache-2.0
import { SETTINGS_SECTIONS } from '@onemind/ui';
import { DOCK_ORDER, PRO_SCREEN_IDS, SCREENS, SCREEN_FILES, SETTINGS_FILES, SETTINGS_PAGES, navIdFor, navItems, screenProblems } from './registry';
import type { ScreenDef } from './types';

const ok: ScreenDef = { id: 'a', path: '/a', title: 'A', icon: 'home', section: 'Your box', order: 1, hue: ['#000', '#fff'], load: async () => ({ default: () => null }) };

describe('screen registry', () => {
  it('every screen file on disk is sound: required fields, one id and one path each', () => {
    expect(Object.keys(SCREEN_FILES).length).toBeGreaterThanOrEqual(16);
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

  it('keeps the nav order, groups, Pro set and dock the shell had before the registry', () => {
    expect(navItems(2).map((n) => [n.id, n.href, n.group ?? 'primary'])).toEqual([
      ['home', '/', 'primary'],
      ['market', '/market', 'primary'],
      ['approvals', '/approvals', 'primary'],
      ['activity', '/activity', 'primary'],
      ['installed', '/installed', 'Your box'],
      ['nodes', '/nodes', 'Your box'],
      ['machines', '/machines', 'Your box'],
      ['alerts', '/alerts', 'Your box'],
      ['storage', '/storage', 'Your box'],
      ['backups', '/backups', 'Your box'],
      ['automation', '/automation', 'Your box'],
      ['updates', '/updates', 'Your box'],
      ['settings', '/settings', 'Your box'],
      ['control-hub', '/control-hub', 'System'],
      ['agents', '/agents', 'System'],
    ]);
    expect(navItems(2).find((n) => n.id === 'approvals')).toMatchObject({ badge: 2, badgeLabel: '2 waiting' });
    expect([...PRO_SCREEN_IDS].sort()).toEqual(['agents', 'automation', 'backups', 'control-hub', 'nodes', 'storage', 'updates']);
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
    expect(navIdFor('/nowhere')).toBe('nowhere');
  });
});

describe('settings registry', () => {
  it('has exactly one page for each @onemind/ui settings section, each with a page or a coming note', () => {
    expect(Object.values(SETTINGS_FILES).length).toBe(SETTINGS_PAGES.size);
    expect([...SETTINGS_PAGES.keys()].sort()).toEqual(SETTINGS_SECTIONS.map((s) => s.id).sort());
    for (const p of SETTINGS_PAGES.values()) expect(!!p.load !== !!p.coming).toBe(true);
  });
});

// SPDX-License-Identifier: Apache-2.0
// @ts-expect-error -- Node built-in; this package has no @types/node. Tests run in Node.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { dark, light } from '../tokens/tokens';
import { clockText, dayPart, greeting, formatUptime, summaryLine } from './greeting';
import { GLASS_ALPHA, HOME_WALLPAPER_IDS, homeWallpapers, wallVar } from './homeTokens';
import {
  DEFAULT_LAYOUT,
  MAX_PINNED,
  MAX_WIDGETS,
  addWidget,
  browserLayoutStore,
  dockApps,
  movePin,
  moveWidget,
  removeWidget,
  resizeWidget,
  sanitizeLayout,
  togglePin,
  type HomeLayout,
} from './layout';
import { CATEGORIES, CATEGORY_SLUGS, categoryOf } from './taxonomy';
import { apps, demoLayout } from '../../demo/src/home/fixtures';

declare const process: { cwd(): string };

const ids = (l: HomeLayout) => l.widgets.map((w) => w.id);

describe('layout', () => {
  it('moves widgets but never the locked "Needs you" or into its place', () => {
    const l = DEFAULT_LAYOUT;
    expect(ids(moveWidget(l, 'w-activity', 1))).toEqual(['w-approvals', 'w-activity', 'w-system', 'w-updates', 'w-backups', 'w-mesh']);
    expect(moveWidget(l, 'w-approvals', 3)).toBe(l);
    expect(ids(moveWidget(l, 'w-system', 0))[0]).toBe('w-approvals');
    expect(moveWidget(l, 'missing', 2)).toBe(l);
    expect(ids(moveWidget(l, 'w-system', 99)).at(-1)).toBe('w-system');
  });

  it('resizes, and refuses unknown sizes', () => {
    expect(resizeWidget(DEFAULT_LAYOUT, 'w-mesh', 'L').widgets.find((w) => w.id === 'w-mesh')!.size).toBe('L');
    expect(resizeWidget(DEFAULT_LAYOUT, 'w-mesh', 'XL' as never)).toBe(DEFAULT_LAYOUT);
  });

  it('removes any widget except the locked one', () => {
    expect(ids(removeWidget(DEFAULT_LAYOUT, 'w-mesh'))).not.toContain('w-mesh');
    expect(removeWidget(DEFAULT_LAYOUT, 'w-approvals')).toBe(DEFAULT_LAYOUT);
  });

  it('adds once, with a unique id, and stops at the limit', () => {
    const a = addWidget(DEFAULT_LAYOUT, { kind: 'system', nodeId: 'n1', size: 'M' });
    expect(a.widgets.at(-1)).toMatchObject({ kind: 'system', nodeId: 'n1', id: 'w-system-n1' });
    expect(addWidget(a, { kind: 'system', nodeId: 'n1', size: 'S' })).toBe(a);
    expect(addWidget(DEFAULT_LAYOUT, { kind: 'mesh', size: 'S' })).toBe(DEFAULT_LAYOUT);
    expect(demoLayout.widgets).toHaveLength(MAX_WIDGETS);
    expect(addWidget(demoLayout, { kind: 'system', nodeId: 'zz', size: 'S' })).toBe(demoLayout);
  });

  it('pins, unpins, reorders the dock, and caps pins', () => {
    let l = togglePin(DEFAULT_LAYOUT, 'a');
    l = togglePin(l, 'b');
    expect(movePin(l, 'b', 0).pinned).toEqual(['b', 'a']);
    expect(togglePin(l, 'a').pinned).toEqual(['b']);
    const full = { ...l, pinned: Array.from({ length: MAX_PINNED }, (_, i) => `p${i}`) };
    expect(togglePin(full, 'extra')).toBe(full);
  });

  it('dock shows installed pinned apps in pin order and skips gone ones', () => {
    const l = { ...DEFAULT_LAYOUT, pinned: ['jellyfin', 'paperless-ngx', 'gone', 'immich'] };
    expect(dockApps(l, apps).map((a) => a.id)).toEqual(['jellyfin', 'immich']);
  });

  it('sanitizes stored layouts: junk gives the default, bad entries are dropped, Needs you goes first', () => {
    expect(sanitizeLayout(null)).toBe(DEFAULT_LAYOUT);
    expect(sanitizeLayout({ version: 2 })).toBe(DEFAULT_LAYOUT);
    const s = sanitizeLayout({
      version: 1,
      widgets: [
        { id: 'x1', kind: 'mesh', size: 'S' },
        { id: 'x1', kind: 'backups', size: 'S' },
        { id: 'x2', kind: 'mesh', size: 'M' },
        { id: 'x3', kind: 'evil', size: 'S' },
        { id: '<script>', kind: 'updates', size: 'S' },
        { id: 'x4', kind: 'app', size: 'S' },
        { id: 'x5', kind: 'updates', size: 'huge' },
        { id: 'x6', kind: 'approvals', size: 'L' },
      ],
      pinned: ['a', 'a', 7, 'b'],
    });
    expect(ids(s)).toEqual(['x6', 'x1', 'x5']);
    expect(s.widgets.find((w) => w.id === 'x5')!.size).toBe('M');
    expect(s.pinned).toEqual(['a', 'b']);
    expect(ids(sanitizeLayout({ version: 1, widgets: [], pinned: [] }))).toEqual(['w-approvals']);
  });

  it('browser store round-trips per person and survives a broken storage', () => {
    const mem = new Map<string, string>();
    const store = browserLayoutStore({ getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => void mem.set(k, v) });
    store.save('person:a', demoLayout);
    expect(store.load('person:a')).toEqual(demoLayout);
    expect(store.load('person:b')).toBeNull();
    const broken = browserLayoutStore({
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('full');
      },
    });
    expect(() => broken.save('p', demoLayout)).not.toThrow();
    expect(broken.load('p')).toBeNull();
  });
});

describe('greeting', () => {
  const at = (iso: string) => Date.parse(iso);
  it('picks the part of the day in the hub time zone', () => {
    expect(dayPart(6)).toBe('morning');
    expect(dayPart(12)).toBe('afternoon');
    expect(dayPart(20)).toBe('evening');
    expect(dayPart(2)).toBe('night');
    expect(greeting(at('2026-11-12T15:04:00Z'), 'Europe/London', 'Robin')).toBe('Good afternoon, Robin');
    expect(greeting(at('2026-11-12T15:04:00Z'), 'Asia/Tokyo')).toBe('Good night');
    expect(greeting(at('2026-11-12T15:04:00Z'), 'Not/AZone', '  ')).toBe('Good afternoon');
    expect(clockText(at('2026-11-12T15:04:00Z'), 'Europe/London')).toBe('15:04');
  });

  it('summarises what needs the person, then what is not fine', () => {
    const base = { waiting: 0, staleNodes: 0, offlineNodes: 0, unhealthyApps: 0, hubLive: true };
    expect(summaryLine(base)).toBe('Everything is running. Nothing needs you.');
    expect(summaryLine({ ...base, waiting: 1 })).toBe('1 request needs your decision.');
    expect(summaryLine({ ...base, waiting: 3, staleNodes: 1, offlineNodes: 1, unhealthyApps: 1 })).toBe('3 requests need your decision; 1 app is unhealthy; 1 stale and 1 offline nodes.');
    expect(summaryLine({ ...base, hubLive: false, waiting: 3 })).toMatch(/last known state/);
  });

  it('formats uptime and says unknown when missing', () => {
    expect(formatUptime(12 * 86_400 + 5 * 3600)).toBe('12 d 5 h');
    expect(formatUptime(3700)).toBe('1 h 1 min');
    expect(formatUptime(undefined)).toBe('unknown');
  });
});

describe('taxonomy', () => {
  it('has the 16 TAXONOMY.md categories in order, and maps legacy slugs from main', () => {
    expect(CATEGORY_SLUGS).toHaveLength(16);
    expect(CATEGORIES.map((c) => c.slug)).toEqual([...CATEGORY_SLUGS]);
    expect(categoryOf('home-automation')?.slug).toBe('home');
    expect(categoryOf('notifications')?.slug).toBe('automation');
    expect(categoryOf('security')?.slug).toBe('network');
    expect(categoryOf('other')).toBeUndefined();
    expect(categoryOf('field')?.name).toBe('Field & Robotics');
  });
});

/* ---------- wallpaper tokens: drift and contrast (WCAG 1.4.3) ---------- */
function rgb(hex: string): [number, number, number] {
  const n = hex.replace('#', '');
  return [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16)) as [number, number, number];
}
function lum([r, g, b]: [number, number, number]): number {
  const f = (c: number) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
const contrast = (a: [number, number, number], b: [number, number, number]) => {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x! + 0.05) / (y! + 0.05);
};
const blend = (top: [number, number, number], under: [number, number, number], alpha: number) => top.map((c, i) => Math.round(c * alpha + under[i]! * (1 - alpha))) as [number, number, number];

describe('home tokens', () => {
  // vitest only processes tokens.css, so `?raw` gives '' here: read the file from disk.
  const css: string = readFileSync(`${process.cwd()}/src/home/home.css`, 'utf8');

  it('home.css carries every wallpaper stop from homeTokens.ts, in both themes', () => {
    for (const theme of ['light', 'dark'] as const)
      for (const id of HOME_WALLPAPER_IDS)
        for (const [stop, val] of Object.entries(homeWallpapers[theme][id])) expect(css).toContain(`${wallVar(id, stop as 'a')}: ${val};`);
    expect(css).toContain(`--omh-glass-alpha: ${GLASS_ALPHA * 100}%;`);
  });

  describe.each([
    ['light', light],
    ['dark', dark],
  ] as const)('%s theme', (theme, t) => {
    it.each(HOME_WALLPAPER_IDS.map((id) => [id]))('%s: greeting text and muted text >= 4.5 on every colour; glass panels too', (id) => {
      for (const stop of Object.values(homeWallpapers[theme][id])) {
        const wall = rgb(stop);
        expect(contrast(rgb(t.text), wall)).toBeGreaterThanOrEqual(4.5);
        expect(contrast(rgb(t['text-muted']), wall)).toBeGreaterThanOrEqual(4.5);
        const glass = blend(rgb(t.surface), wall, GLASS_ALPHA);
        for (const fg of ['text', 'text-muted', 'text-subtle', 'accent'] as const) expect(contrast(rgb(t[fg]), glass)).toBeGreaterThanOrEqual(4.5);
      }
    });
  });
});

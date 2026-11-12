// SPDX-License-Identifier: Apache-2.0
// Logic of the customization engine: colour maths, the AA fix, wallpaper contrast guard,
// preferences validation, schedule, CSS output, DOM application and both store adapters.
import { describe, expect, it, vi } from 'vitest';
import { dark, light } from '../tokens/tokens';
import { AA, ACCENTS, ACCENT_IDS, DEFAULT_ACCENT, accentWorstRatio, customAccent, deriveAccent, presetAccent } from './accents';
import { contrast, hexToOklch, mix, normalizeHex, oklchToHex } from './color';
import {
  DEFAULT_PREFERENCES,
  STYLE_ID,
  accentSeed,
  applyPreferences,
  clearPreferences,
  customizeCss,
  effectiveDim,
  msUntilNextSwitch,
  normalizePreferences,
  resolveThemeAttr,
  scheduledTheme,
} from './preferences';
import { ApiPreferencesStore, LocalPreferencesStore, LOCAL_SLOT, PreferencesError } from './store';
import { checkUpload, sampleColors } from './upload';
import { UNKNOWN_IMAGE_MIN_DIM, WALLPAPERS, WALLPAPER_IDS, minDim, paintedColors } from './wallpapers';

const THEMES = ['light', 'dark'] as const;

describe('colour maths', () => {
  it('computes WCAG contrast', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
    expect(contrast('#ffffff', '#ffffff')).toBe(1);
  });
  it('normalises hex and rejects junk', () => {
    expect(normalizeHex('#ABC')).toBe('#aabbcc');
    expect(normalizeHex('1f6a66')).toBe('#1f6a66');
    expect(normalizeHex('red')).toBeNull();
    expect(normalizeHex('#12345')).toBeNull();
  });
  it('round-trips through OKLCH', () => {
    for (const hex of ['#1f6a66', '#a02c5a', '#ffffff', '#000000', '#3f4b55']) {
      expect(oklchToHex(hexToOklch(hex))).toBe(hex);
    }
  });
  it('mixes in sRGB', () => {
    expect(mix('#ffffff', '#000000', 0.5)).toBe('#808080');
    expect(mix('#ff0000', '#0000ff', 1)).toBe('#ff0000');
  });
});

describe('accents', () => {
  it('ships the brand accent plus 8 curated presets, all passing AA untouched in both themes', () => {
    expect(ACCENT_IDS).toHaveLength(9);
    expect(ACCENT_IDS[0]).toBe('onemind');
    for (const id of ACCENT_IDS) {
      const a = presetAccent(id);
      for (const t of THEMES) {
        expect(a[t].ratio, `${id} ${t}`).toBeGreaterThanOrEqual(AA);
        expect(a[t].adjusted, `${id} ${t} should not need a fix`).toBe(false);
        expect(a[t].set.accent).toBe(ACCENTS[id][t]);
      }
    }
  });
  it('the default (brand) preset equals the shipped tokens, all four roles', () => {
    expect(DEFAULT_ACCENT).toBe('onemind');
    const a = presetAccent(DEFAULT_ACCENT);
    for (const [t, theme] of [['light', light], ['dark', dark]] as const) {
      expect(a[t].set).toEqual({ accent: theme.accent, hover: theme['accent-hover'], text: theme['accent-text'], soft: theme['accent-soft'] });
    }
  });
  it('fixes any custom colour to AA, keeping its hue', () => {
    const samples = ['#ffff00', '#ffffff', '#000000', '#00ff00', '#ff00ff', '#7fdbff', '#ff851b', '#111111', '#e0e0e0', '#2ecc40'];
    for (const hex of samples) {
      const c = customAccent(hex);
      for (const t of THEMES) {
        expect(accentWorstRatio(c[t].set, t), `${hex} ${t}`).toBeGreaterThanOrEqual(AA);
      }
    }
    const y = deriveAccent('#ffd400', 'light');
    expect(y.adjusted).toBe(true);
    expect(Math.abs(hexToOklch(y.set.accent).h - hexToOklch('#ffd400').h)).toBeLessThan(12);
  });
  it('checks text on accent and hover too', () => {
    for (const t of THEMES) {
      const d = deriveAccent('#3366ff', t);
      expect(contrast(d.set.text, d.set.accent)).toBeGreaterThanOrEqual(AA);
      expect(contrast(d.set.text, d.set.hover)).toBeGreaterThanOrEqual(AA);
      expect(contrast(d.set.accent, d.set.soft)).toBeGreaterThanOrEqual(AA);
    }
  });
});

describe('wallpapers', () => {
  it('has 10+ generated wallpapers with unique ids and a known accent', () => {
    expect(WALLPAPER_IDS.length).toBeGreaterThanOrEqual(10);
    expect(new Set(WALLPAPER_IDS).size).toBe(WALLPAPER_IDS.length);
    for (const id of WALLPAPER_IDS) {
      const w = WALLPAPERS[id];
      expect(w.id).toBe(id);
      expect(ACCENT_IDS).toContain(w.accent);
      for (const t of THEMES) {
        const css = w.render(w.colors[t]);
        expect(css.length).toBeGreaterThan(20);
        expect(css).not.toMatch(/https?:\/\//); // generated: no external asset
      }
    }
  });
  it('renders deterministically', () => {
    for (const id of WALLPAPER_IDS) expect(WALLPAPERS[id].render(WALLPAPERS[id].colors.light)).toBe(WALLPAPERS[id].render(WALLPAPERS[id].colors.light));
  });
  it('text, muted text and every accent stay AA over every wallpaper at its effective dim (all pairs)', () => {
    const seeds = [...ACCENT_IDS.map((id) => ({ id, a: presetAccent(id) })), { id: 'custom-yellow', a: customAccent('#ffd400') }];
    for (const wid of WALLPAPER_IDS) {
      for (const { id, a } of seeds) {
        const p = normalizePreferences({ wallpaper: wid, wallpaperDim: 0, accentSource: 'preset', accentPreset: ACCENT_IDS.includes(id as never) ? id : 'teal' });
        for (const t of THEMES) {
          const accent = a[t].set.accent;
          const { dim } = effectiveDim(p, t, accent);
          const veil = t === 'light' ? light.bg : dark.bg;
          for (const c of paintedColors(WALLPAPERS[wid].colors[t])) {
            const under = mix(veil, c, dim);
            const tokens = t === 'light' ? light : dark;
            expect(contrast(tokens.text, under), `${wid}/${id}/${t} text`).toBeGreaterThanOrEqual(AA);
            expect(contrast(tokens['text-muted'], under), `${wid}/${id}/${t} muted`).toBeGreaterThanOrEqual(AA);
            expect(contrast(accent, under), `${wid}/${id}/${t} accent`).toBeGreaterThanOrEqual(AA);
          }
        }
      }
    }
  });
  it('raises the dim only when needed and uses a safe default for unknown images', () => {
    expect(minDim(null, 'dark')).toBe(UNKNOWN_IMAGE_MIN_DIM);
    expect(minDim([light.bg], 'light')).toBe(0);
    const p = normalizePreferences({ wallpaper: 'custom', wallpaperDim: 0.1 });
    expect(effectiveDim(p, 'light')).toEqual({ dim: UNKNOWN_IMAGE_MIN_DIM, min: UNKNOWN_IMAGE_MIN_DIM, raised: true });
    expect(effectiveDim(normalizePreferences({ wallpaper: 'none' }), 'dark').dim).toBe(0);
  });
});

describe('preferences', () => {
  it('normalises junk field by field', () => {
    const p = normalizePreferences({ theme: 'neon', accentPreset: 'rose', wallpaper: 'mars', wallpaperBlur: 999, wallpaperDim: -1, fontScale: 3, schedule: { darkFrom: '25:00', lightFrom: '06:30' }, customWallpaperColors: ['#fff', 'nope'] });
    expect(p.theme).toBe('system');
    expect(p.accentPreset).toBe('rose');
    expect(p.wallpaper).toBe(DEFAULT_PREFERENCES.wallpaper);
    expect(p.wallpaperBlur).toBe(40);
    expect(p.wallpaperDim).toBe(0);
    expect(p.fontScale).toBe(1);
    expect(p.schedule).toEqual({ darkFrom: '19:00', lightFrom: '06:30' });
    expect(p.customWallpaperColors).toEqual(['#ffffff']);
    expect(normalizePreferences(null)).toEqual(DEFAULT_PREFERENCES);
    expect(normalizePreferences('x')).toEqual(DEFAULT_PREFERENCES);
  });
  it('resolves the schedule across midnight', () => {
    const s = { darkFrom: '19:00', lightFrom: '07:00' };
    const at = (h: number, m = 0) => new Date(2026, 10, 12, h, m);
    expect(scheduledTheme(s, at(6, 59))).toBe('dark');
    expect(scheduledTheme(s, at(7))).toBe('light');
    expect(scheduledTheme(s, at(18, 59))).toBe('light');
    expect(scheduledTheme(s, at(19))).toBe('dark');
    expect(scheduledTheme({ darkFrom: '01:00', lightFrom: '05:00' }, at(3))).toBe('dark');
    expect(scheduledTheme({ darkFrom: '01:00', lightFrom: '05:00' }, at(12))).toBe('light');
    expect(msUntilNextSwitch(s, at(18, 30))).toBe(30 * 60_000);
    expect(msUntilNextSwitch(s, at(19, 0))).toBe(12 * 3600_000);
  });
  it('resolves theme attribute and accent seed', () => {
    const at = new Date(2026, 10, 12, 22, 0);
    expect(resolveThemeAttr(DEFAULT_PREFERENCES, at)).toBeNull();
    expect(resolveThemeAttr({ ...DEFAULT_PREFERENCES, theme: 'dark' }, at)).toBe('dark');
    expect(resolveThemeAttr({ ...DEFAULT_PREFERENCES, theme: 'schedule' }, at)).toBe('dark');
    expect(accentSeed({ ...DEFAULT_PREFERENCES, accentSource: 'wallpaper', wallpaper: 'dunes' })).toEqual({ kind: 'preset', id: 'copper' });
    expect(accentSeed(DEFAULT_PREFERENCES)).toEqual({ kind: 'preset', id: 'onemind' });
    expect(accentSeed({ ...DEFAULT_PREFERENCES, accentSource: 'wallpaper', wallpaper: 'none' })).toEqual({ kind: 'preset', id: 'onemind' });
    expect(accentSeed({ ...DEFAULT_PREFERENCES, accentSource: 'custom', accentCustom: '#123456' })).toEqual({ kind: 'custom', hex: '#123456' });
  });
  it('writes CSS that mirrors the token theme selectors', () => {
    const css = customizeCss({ ...DEFAULT_PREFERENCES, accentSource: 'preset', accentPreset: 'rose', corners: 'round' });
    expect(css).toContain(`--om-color-accent: ${ACCENTS.rose.light};`);
    expect(css).toContain(`--om-color-accent: ${ACCENTS.rose.dark};`);
    expect(css).toContain(":root:root[data-theme='dark']");
    expect(css).toContain('@media (prefers-color-scheme: dark)');
    expect(css).toContain('--om-radius-lg: 20px;');
    expect(customizeCss(DEFAULT_PREFERENCES)).not.toContain('--om-radius');
  });
  it('applies to and clears from the root', () => {
    const root = document.documentElement;
    applyPreferences({ ...DEFAULT_PREFERENCES, theme: 'dark', density: 'compact', fontScale: 1.25, transparency: 'system' }, { systemReducedTransparency: true });
    expect(root.getAttribute('data-theme')).toBe('dark');
    expect(root.getAttribute('data-om-density')).toBe('compact');
    expect(root.getAttribute('data-om-glass')).toBe('off');
    expect(root.style.fontSize).toBe('125%');
    expect(document.getElementById(STYLE_ID)?.textContent).toContain('--om-color-accent');
    applyPreferences({ ...DEFAULT_PREFERENCES, transparency: 'on' });
    expect(root.hasAttribute('data-theme')).toBe(false);
    expect(root.getAttribute('data-om-glass')).toBe('on');
    expect(root.style.fontSize).toBe('');
    clearPreferences();
    expect(root.hasAttribute('data-om-density')).toBe(false);
    expect(document.getElementById(STYLE_ID)).toBeNull();
  });
});

function memoryStorage(fail?: 'all' | 'quota'): Storage {
  const m = new Map<string, string>();
  return {
    get length() {
      return m.size;
    },
    clear: () => m.clear(),
    key: (i: number) => [...m.keys()][i] ?? null,
    getItem: (k: string) => {
      if (fail === 'all') throw new Error('SecurityError');
      return m.get(k) ?? null;
    },
    setItem: (k: string, v: string) => {
      if (fail === 'all') throw new Error('SecurityError');
      if (fail === 'quota') throw Object.assign(new Error('full'), { name: 'QuotaExceededError' });
      m.set(k, v);
    },
    removeItem: (k: string) => void m.delete(k),
  };
}

describe('LocalPreferencesStore', () => {
  const clock = () => new Date('2026-11-12T15:00:00Z');
  it('returns defaults with no updatedAt when empty, and round-trips', async () => {
    const s = new LocalPreferencesStore({ storage: memoryStorage(), clock });
    expect(await s.load()).toEqual({ prefs: DEFAULT_PREFERENCES, updatedAt: null });
    const p = { ...DEFAULT_PREFERENCES, accentSource: 'preset' as const, accentPreset: 'moss' as const };
    expect(await s.save(p)).toEqual({ prefs: p, updatedAt: '2026-11-12T15:00:00.000Z' });
    expect(await s.load()).toEqual({ prefs: p, updatedAt: '2026-11-12T15:00:00.000Z' });
  });
  it('survives corrupted JSON', async () => {
    const st = memoryStorage();
    st.setItem(LOCAL_SLOT, '{nope');
    expect((await new LocalPreferencesStore({ storage: st }).load()).prefs).toEqual(DEFAULT_PREFERENCES);
  });
  it('reports blocked storage and a full quota in plain words', async () => {
    await expect(new LocalPreferencesStore({ storage: null }).load()).rejects.toMatchObject({ code: 'storage_unavailable' });
    await expect(new LocalPreferencesStore({ storage: memoryStorage('all') }).load()).rejects.toMatchObject({ code: 'storage_unavailable' });
    await expect(new LocalPreferencesStore({ storage: memoryStorage('quota') }).save(DEFAULT_PREFERENCES)).rejects.toMatchObject({ code: 'quota_exceeded' });
    await expect(new LocalPreferencesStore({ storage: memoryStorage('quota') }).saveWallpaperImage('data:image/jpeg;base64,AA')).rejects.toBeInstanceOf(PreferencesError);
  });
});

describe('ApiPreferencesStore (pending contract §12)', () => {
  const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
  it('GETs and PUTs /v1/me/preferences with the bearer token', async () => {
    const f = vi.fn<typeof fetch>(async (_u, init) =>
      init?.method === 'PUT' ? json(200, { appearance: JSON.parse(String(init.body)).appearance, updated_at: '2026-11-12T15:00:00Z' }) : json(200, { appearance: { theme: 'dark' }, updated_at: '2026-11-12T14:00:00Z' }),
    );
    const s = new ApiPreferencesStore({ baseUrl: 'https://box.example/', token: () => 't0k', fetch: f });
    const got = await s.load();
    expect(got.prefs.theme).toBe('dark');
    expect(got.updatedAt).toBe('2026-11-12T14:00:00Z');
    expect(f.mock.calls[0]![0]).toBe('https://box.example/v1/me/preferences');
    expect((f.mock.calls[0]![1]!.headers as Record<string, string>).authorization).toBe('Bearer t0k');
    const saved = await s.save({ ...DEFAULT_PREFERENCES, density: 'compact' });
    expect(saved.prefs.density).toBe('compact');
    expect(f.mock.calls[1]![1]!.method).toBe('PUT');
  });
  it('maps errors: 404 is the pending contract, 401, 403, network and bad bodies', async () => {
    const at = (r: Response | Error) => new ApiPreferencesStore({ fetch: async () => (r instanceof Error ? Promise.reject(r) : r) });
    await expect(at(json(404, {})).load()).rejects.toMatchObject({ code: 'pending_contract' });
    await expect(at(json(401, {})).load()).rejects.toMatchObject({ code: 'unauthenticated' });
    await expect(at(json(403, {})).load()).rejects.toMatchObject({ code: 'permission_denied' });
    await expect(at(new TypeError('offline')).load()).rejects.toMatchObject({ code: 'network' });
    await expect(at(json(200, { nope: 1 })).load()).rejects.toMatchObject({ code: 'invalid_response' });
  });
});

describe('upload', () => {
  it('checks type and size', () => {
    expect(checkUpload({ type: 'image/gif', size: 10 })).toMatch(/JPEG, PNG or WebP/);
    expect(checkUpload({ type: 'image/png', size: 11 * 1024 * 1024 })).toMatch(/10 MB/);
    expect(checkUpload({ type: 'image/png', size: 0 })).toMatch(/empty/);
    expect(checkUpload({ type: 'image/webp', size: 2048 })).toBeNull();
  });
  it('samples representative colours and skips transparent pixels', () => {
    const px = [0, 0, 0, 255, 255, 255, 255, 255, 128, 128, 128, 255, 10, 200, 10, 0];
    const c = sampleColors(px);
    expect(c).toContain('#000000');
    expect(c).toContain('#ffffff');
    expect(c).not.toContain('#0ac80a');
    expect(sampleColors([])).toEqual([]);
  });
});

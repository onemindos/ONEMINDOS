// SPDX-License-Identifier: Apache-2.0
// OneMind's own wallpapers. Every one is generated here as CSS gradients or a small inline SVG
// from a seeded random function: no image files, no third-party art, nothing traced.
// Each wallpaper declares the colours it paints with, per theme, and an accent preset, so
// "Match wallpaper" can re-tint the UI and the contrast guard can compute how much dimming
// text needs to stay readable on top of it.
import { dark, light } from '../tokens/tokens';
import type { AccentId, ThemeName } from './accents';
import { AA } from './accents';
import { contrast, mix } from './color';

export const WALLPAPER_IDS = [
  'aurora',
  'tide',
  'contour',
  'dunes',
  'fjord',
  'signal',
  'nebula',
  'meadow',
  'dusk',
  'bloom',
  'lattice',
  'paper',
] as const;
export type WallpaperId = (typeof WALLPAPER_IDS)[number];
export type WallpaperChoice = WallpaperId | 'none' | 'custom';

export type WallpaperKind = 'mesh' | 'gradient' | 'pattern' | 'landscape';

/** Four colours: [base, a, b, c]. Everything the wallpaper paints is one of these or a blend. */
export type Stops = readonly [string, string, string, string];

export interface Wallpaper {
  id: WallpaperId;
  name: string;
  kind: WallpaperKind;
  accent: AccentId;
  colors: Record<ThemeName, Stops>;
  /** CSS `background` value for the given stops. */
  render: (c: Stops) => string;
}

/** Deterministic pseudo-random numbers (mulberry32), so a wallpaper looks the same everywhere. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const r1 = (n: number) => Math.round(n * 10) / 10;

export function svgUrl(svg: string): string {
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

const VB = 'viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice"';
const svg = (body: string) => `<svg xmlns="http://www.w3.org/2000/svg" ${VB}>${body}</svg>`;

function waves(c: Stops, seed: number): string {
  const rand = rng(seed);
  const layers = [c[1], c[2], c[3], c[2]];
  const paths = layers.map((fill, i) => {
    const y0 = 420 + i * 150;
    const amp = 40 + rand() * 50;
    const freq = 1.2 + rand() * 1.4;
    const phase = rand() * Math.PI * 2;
    let d = `M0 ${y0}`;
    for (let x = 0; x <= 1600; x += 40) d += ` L${x} ${r1(y0 + Math.sin((x / 1600) * Math.PI * 2 * freq + phase) * amp)}`;
    d += ' L1600 1000 L0 1000Z';
    return `<path d="${d}" fill="${fill}" fill-opacity="${0.55 + i * 0.12}"/>`;
  });
  return svg(`<rect width="1600" height="1000" fill="${c[0]}"/>${paths.join('')}`);
}

function contours(c: Stops, seed: number): string {
  const rand = rng(seed);
  const centres = [
    [480, 380],
    [1180, 640],
  ] as const;
  const rings: string[] = [];
  centres.forEach(([cx, cy], k) => {
    const wob = Array.from({ length: 6 }, () => rand() * Math.PI * 2);
    for (let i = 1; i <= 14; i++) {
      const base = i * 42;
      let d = '';
      for (let a = 0; a <= 72; a++) {
        const t = (a / 72) * Math.PI * 2;
        const rr = base * (1 + 0.12 * Math.sin(3 * t + wob[0]!) + 0.07 * Math.sin(5 * t + wob[1]!) + 0.04 * Math.sin(2 * t + wob[2]!));
        d += `${a ? 'L' : 'M'}${r1(cx + Math.cos(t) * rr * 1.3)} ${r1(cy + Math.sin(t) * rr)}`;
      }
      rings.push(`<path d="${d}Z" fill="none" stroke="${k ? c[2] : c[1]}" stroke-width="${i % 5 === 0 ? 2.4 : 1.2}" stroke-opacity="0.8"/>`);
    }
  });
  return svg(`<rect width="1600" height="1000" fill="${c[0]}"/>${rings.join('')}<circle cx="1420" cy="140" r="160" fill="${c[3]}" fill-opacity="0.35"/>`);
}

function ridges(c: Stops, seed: number, peaks: number): string {
  const rand = rng(seed);
  const layers = [c[3], c[2], c[1]];
  const out = layers.map((fill, i) => {
    const base = 520 + i * 160;
    let d = `M0 ${base}`;
    const n = peaks + i * 2;
    for (let k = 0; k <= n; k++) {
      const x = (k / n) * 1600;
      const y = base - (k % 2 ? 120 + rand() * 180 - i * 30 : rand() * 60);
      d += ` L${r1(x)} ${r1(y)}`;
    }
    return `<path d="${d} L1600 1000 L0 1000Z" fill="${fill}"/>`;
  });
  return svg(`<rect width="1600" height="1000" fill="${c[0]}"/><circle cx="1180" cy="300" r="110" fill="${c[3]}" fill-opacity="0.5"/>${out.join('')}`);
}

function dunes(c: Stops, seed: number): string {
  const rand = rng(seed);
  const layers = [c[1], c[2], c[3]];
  const out = layers.map((fill, i) => {
    const y = 460 + i * 170;
    const cx1 = rand() * 800;
    const cx2 = 800 + rand() * 800;
    return `<path d="M0 ${y} C ${r1(cx1)} ${y - 220} ${r1(cx2)} ${y + 200} 1600 ${y - 60} L1600 1000 L0 1000Z" fill="${fill}"/>`;
  });
  return svg(`<rect width="1600" height="1000" fill="${c[0]}"/>${out.join('')}`);
}

function rings(c: Stops, cx: number, cy: number, n: number, gap: number): string {
  const out: string[] = [];
  for (let i = 1; i <= n; i++) {
    out.push(`<circle cx="${cx}" cy="${cy}" r="${i * gap}" fill="none" stroke="${i % 3 ? c[1] : c[2]}" stroke-width="${i % 3 ? 1.5 : 3}" stroke-opacity="0.75"/>`);
  }
  return out.join('');
}

function bloom(c: Stops): string {
  const petals: string[] = [];
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * 360;
    petals.push(`<ellipse cx="800" cy="500" rx="420" ry="120" fill="${i % 2 ? c[1] : c[2]}" fill-opacity="0.22" transform="rotate(${a} 800 500)"/>`);
  }
  return svg(`<rect width="1600" height="1000" fill="${c[0]}"/>${petals.join('')}<circle cx="800" cy="500" r="90" fill="${c[3]}" fill-opacity="0.5"/>`);
}

const radial = (x: string, y: string, color: string, size = '55%') => `radial-gradient(circle at ${x} ${y}, ${color} 0, transparent ${size})`;

export const WALLPAPERS: Record<WallpaperId, Wallpaper> = {
  aurora: {
    id: 'aurora',
    name: 'Aurora',
    kind: 'mesh',
    accent: 'teal',
    colors: { light: ['#e4f1ef', '#a9d8d1', '#c4d4f3', '#e9e1c9'], dark: ['#0b1719', '#14504b', '#1d2f5c', '#2c4a3a'] },
    render: (c) => `${radial('15%', '20%', c[1])}, ${radial('85%', '15%', c[2])}, ${radial('70%', '90%', c[3], '60%')}, ${c[0]}`,
  },
  tide: {
    id: 'tide',
    name: 'Tide',
    kind: 'landscape',
    accent: 'lagoon',
    colors: { light: ['#e6f2f7', '#b3dcea', '#8ec6dc', '#cde8f1'], dark: ['#08141c', '#0f3a52', '#155a78', '#0b2a3c'] },
    render: (c) => `${svgUrl(waves(c, 7))} center / cover no-repeat, ${c[0]}`,
  },
  contour: {
    id: 'contour',
    name: 'Contour',
    kind: 'pattern',
    accent: 'moss',
    colors: { light: ['#eef2e6', '#b9c99c', '#c9d6b3', '#dfe8c9'], dark: ['#10150b', '#3a4d22', '#2c3b1a', '#4b6128'] },
    render: (c) => `${svgUrl(contours(c, 11))} center / cover no-repeat, ${c[0]}`,
  },
  dunes: {
    id: 'dunes',
    name: 'Dunes',
    kind: 'landscape',
    accent: 'copper',
    colors: { light: ['#f6ece3', '#efcfb6', '#e3b393', '#d99f7c'], dark: ['#1a110c', '#4a2a19', '#5e3420', '#3a2014'] },
    render: (c) => `${svgUrl(dunes(c, 3))} center / cover no-repeat, ${c[0]}`,
  },
  fjord: {
    id: 'fjord',
    name: 'Fjord',
    kind: 'landscape',
    accent: 'ink',
    colors: { light: ['#e9edf8', '#9fb0dc', '#bcc8e8', '#d6def3'], dark: ['#0b0f1c', '#24315e', '#1a2447', '#33427a'] },
    render: (c) => `${svgUrl(ridges(c, 5, 8))} center / cover no-repeat, ${c[0]}`,
  },
  signal: {
    id: 'signal',
    name: 'Signal',
    kind: 'pattern',
    accent: 'teal',
    colors: { light: ['#eef4f3', '#b6d6d2', '#8fc3bc', '#d8ebe8'], dark: ['#0a1213', '#1d4743', '#2a6660', '#14302d'] },
    render: (c) =>
      `${svgUrl(svg(`<rect width="1600" height="1000" fill="${c[0]}"/>${rings(c, 1400, 860, 26, 46)}<circle cx="1400" cy="860" r="22" fill="${c[2]}"/>`))} center / cover no-repeat, ${c[0]}`,
  },
  nebula: {
    id: 'nebula',
    name: 'Nebula',
    kind: 'mesh',
    accent: 'orchid',
    colors: { light: ['#f3ecf3', '#e2c3df', '#c9cdef', '#f0d6e2'], dark: ['#120c16', '#4a2148', '#24285a', '#3d1a33'] },
    render: (c) => `${radial('80%', '25%', c[1], '50%')}, ${radial('20%', '75%', c[2], '55%')}, ${radial('55%', '55%', c[3], '45%')}, ${c[0]}`,
  },
  meadow: {
    id: 'meadow',
    name: 'Meadow',
    kind: 'mesh',
    accent: 'moss',
    colors: { light: ['#f0f4e7', '#cfe0ad', '#e7e1b4', '#bfd8c3'], dark: ['#0e140b', '#33461d', '#45421c', '#1e3a2a'] },
    render: (c) => `${radial('10%', '90%', c[1], '60%')}, ${radial('90%', '80%', c[2], '50%')}, ${radial('60%', '10%', c[3], '55%')}, ${c[0]}`,
  },
  dusk: {
    id: 'dusk',
    name: 'Dusk',
    kind: 'gradient',
    accent: 'rose',
    colors: { light: ['#f7e9ee', '#efc6d4', '#f2d7c2', '#e0b3c4'], dark: ['#160b11', '#4d1d33', '#4a2a22', '#2e1322'] },
    render: (c) =>
      `${svgUrl(svg(`<circle cx="1200" cy="640" r="220" fill="${c[3]}" fill-opacity="0.55"/>`))} center / cover no-repeat, linear-gradient(170deg, ${c[0]} 0%, ${c[1]} 55%, ${c[2]} 100%)`,
  },
  bloom: {
    id: 'bloom',
    name: 'Bloom',
    kind: 'pattern',
    accent: 'rose',
    colors: { light: ['#f8eef1', '#e9b9c9', '#e8cfb9', '#d98fa8'], dark: ['#150a0e', '#5a2238', '#4f3322', '#7a2e4b'] },
    render: (c) => `${svgUrl(bloom(c))} center / cover no-repeat, ${c[0]}`,
  },
  lattice: {
    id: 'lattice',
    name: 'Lattice',
    kind: 'pattern',
    accent: 'graphite',
    colors: { light: ['#f1f3f4', '#c3cbd0', '#dde3e6', '#e7ebed'], dark: ['#0d1112', '#2f393e', '#1a2124', '#232b2f'] },
    render: (c) =>
      `radial-gradient(${c[1]} 1.2px, transparent 1.6px) 0 0 / 22px 22px, linear-gradient(160deg, ${c[3]} 0%, ${c[0]} 50%, ${c[2]} 100%)`,
  },
  paper: {
    id: 'paper',
    name: 'Paper',
    kind: 'pattern',
    accent: 'ink',
    colors: { light: ['#f6f5f1', '#e4e1d8', '#ece9e1', '#d9d5ca'], dark: ['#111213', '#1f2123', '#191a1c', '#2a2c2f'] },
    render: (c) =>
      `repeating-linear-gradient(135deg, ${c[1]} 0 1px, transparent 1px 14px), radial-gradient(circle at 50% 40%, ${c[0]} 0, ${c[2]} 70%, ${c[3]} 100%)`,
  },
};

export function isWallpaperChoice(v: unknown): v is WallpaperChoice {
  return v === 'none' || v === 'custom' || (typeof v === 'string' && (WALLPAPER_IDS as readonly string[]).includes(v));
}

/** Theme colours whose contrast against the wallpaper must hold: body text and muted text. */
const TEXT: Record<ThemeName, string[]> = {
  light: [light.text, light['text-muted']],
  dark: [dark.text, dark['text-muted']],
};
const VEIL: Record<ThemeName, string> = { light: light.bg, dark: dark.bg };

/** Every colour that can appear under text: the stops plus each pairwise midpoint. */
export function paintedColors(stops: readonly string[]): string[] {
  const out = [...stops];
  for (let i = 0; i < stops.length; i++) for (let j = i + 1; j < stops.length; j++) out.push(mix(stops[i]!, stops[j]!, 0.5));
  return out;
}

/** Dim used when the colours are unknown (an uploaded image that could not be sampled). */
export const UNKNOWN_IMAGE_MIN_DIM = 0.6;

/**
 * The smallest dim (0..0.95, in steps of 0.05) at which body text, muted text and the accent
 * all reach 4.5:1 on every painted colour once the theme-coloured veil is laid over it.
 * Dimming blends the wallpaper towards the page background, so light themes "fade" it and
 * dark themes "darken" it.
 */
export function minDim(stops: readonly string[] | null, theme: ThemeName, accent?: string): number {
  if (!stops || stops.length === 0) return UNKNOWN_IMAGE_MIN_DIM;
  const colors = paintedColors(stops);
  const fg = accent ? [...TEXT[theme], accent] : TEXT[theme];
  for (let step = 0; step <= 19; step++) {
    const d = step * 0.05;
    const ok = colors.every((c) => {
      const under = mix(VEIL[theme], c, d);
      return fg.every((f) => contrast(f, under) >= AA);
    });
    if (ok) return Math.round(d * 100) / 100;
  }
  return 0.95;
}

export function wallpaperBackground(id: WallpaperId, theme: ThemeName): string {
  const w = WALLPAPERS[id];
  return w.render(w.colors[theme]);
}

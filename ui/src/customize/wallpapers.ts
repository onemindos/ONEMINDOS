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

/** Console's set from the founder's final design comes first (Contour is the default); the
 * earlier OneMind wallpapers after it stay selectable so nobody loses a saved choice. */
export const CONSOLE_WALLPAPERS = ['contour', 'ripple', 'signal', 'dawn', 'harvest', 'mycelium', 'lattice', 'ember'] as const;
export const WALLPAPER_IDS = [
  ...CONSOLE_WALLPAPERS,
  'onemind',
  'aurora',
  'tide',
  'dunes',
  'fjord',
  'nebula',
  'meadow',
  'dusk',
  'bloom',
  'paper',
] as const;
export type WallpaperId = (typeof WALLPAPER_IDS)[number];
export type WallpaperChoice = WallpaperId | 'none' | 'custom';

export type WallpaperKind = 'mesh' | 'gradient' | 'pattern' | 'landscape';

/** At least four colours: [base, a, b, c, ...more]. Everything the wallpaper paints is one of
 * these or a blend of two, so the contrast guard sees every colour under text. */
export type Stops = readonly [string, string, string, string, ...string[]];

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

function bloom(c: Stops): string {
  const petals: string[] = [];
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * 360;
    petals.push(`<ellipse cx="800" cy="500" rx="420" ry="120" fill="${i % 2 ? c[1] : c[2]}" fill-opacity="0.22" transform="rotate(${a} 800 500)"/>`);
  }
  return svg(`<rect width="1600" height="1000" fill="${c[0]}"/>${petals.join('')}<circle cx="800" cy="500" r="90" fill="${c[3]}" fill-opacity="0.5"/>`);
}

const radial = (x: string, y: string, color: string, size = '55%') => `radial-gradient(circle at ${x} ${y}, ${color} 0, transparent ${size})`;

/**
 * OneMind's signature: a quiet neural field. Seeded nodes, each linked to its nearest
 * neighbours with hairlines, densest towards the top left where the brand glow sits.
 * Lines and nodes use the wallpaper's own stops, so the contrast guard sees every colour.
 */
function neural(c: Stops, seed: number): string {
  const rand = rng(seed);
  const W = 1600;
  const H = 1000;
  const pts = Array.from({ length: 46 }, () => {
    // bias towards the upper-left third, like the glow
    const x = Math.pow(rand(), 1.35) * W;
    const y = Math.pow(rand(), 1.2) * H;
    return [r1(x), r1(y)] as const;
  });
  const lines: string[] = [];
  pts.forEach(([x, y], i) => {
    const near = pts
      .map(([u, v], j) => ({ j, d: (u - x) ** 2 + (v - y) ** 2 }))
      .filter((n) => n.j > i)
      .sort((a, b) => a.d - b.d)
      .slice(0, 2);
    for (const n of near) {
      const [u, v] = pts[n.j]!;
      lines.push(`<line x1="${x}" y1="${y}" x2="${u}" y2="${v}"/>`);
    }
  });
  const dots = pts.map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="${i % 7 === 0 ? 3.2 : 1.6}"/>`).join('');
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice">` +
    `<g stroke="${c[3]}" stroke-width="1" stroke-opacity="0.55" fill="none">${lines.join('')}</g>` +
    `<g fill="${c[1]}" fill-opacity="0.9">${dots}</g></svg>`;
  return svgUrl(svg);
}

/*
 * Console's procedural set, ported from the founder's final design (design-v2/final/lib/walls.js,
 * OneMind's own artwork). Semi-transparent strokes there are drawn here in their composited,
 * opaque colour, so each stop is a colour that is really on screen.
 */
const CW = 1440;
const CH = 900;
const wall = (defs: string, body: string) =>
  svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${CW} ${CH}" preserveAspectRatio="xMidYMid slice"><defs>${defs}</defs><rect width="${CW}" height="${CH}" fill="url(#bg)"/>${body}</svg>`);
const lin = (id: string, stops: [number, string][], x2 = 1, y2 = 1) =>
  `<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}">${stops.map(([o, col]) => `<stop offset="${o}" stop-color="${col}"/>`).join('')}</linearGradient>`;
const glow = (id: string, col: string) => `<radialGradient id="${id}"><stop offset="0" stop-color="${col}"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></radialGradient>`;
const cover = (url: string, base: string) => `${url} center / cover no-repeat, ${base}`;

function consoleContour(c: Stops): string {
  const ringSet = (cx: number, cy: number, n: number, seed: number) => {
    let out = '';
    for (let i = 0; i < n; i++) {
      const base = 30 + i * 30;
      let d = '';
      for (let k = 0; k <= 120; k++) {
        const a = (k / 120) * Math.PI * 2;
        const rr = base * (1 + 0.09 * Math.sin(3 * a + i * 0.35 + seed) + 0.05 * Math.sin(5 * a - i * 0.22) + 0.03 * Math.cos(7 * a + seed));
        d += `${k ? 'L' : 'M'}${r1(cx + Math.cos(a) * rr * 1.25)} ${r1(cy + Math.sin(a) * rr)}`;
      }
      const hot = i % 7 === 4;
      out += `<path d="${d}Z" fill="none" stroke="${hot ? c[3] : c[1]}" stroke-width="${hot ? 1.3 : 1}"/>`;
    }
    return out;
  };
  return cover(wall(lin('bg', [[0, c[0]], [1, c[2]]]), ringSet(1010, 360, 26, 0.4) + ringSet(260, 860, 16, 2.1)), c[0]);
}

function consoleRipple(c: Stops): string {
  const cx = 1010;
  const cy = 400;
  let body = `<circle cx="260" cy="860" r="620" fill="url(#g)" opacity="0.8"/><circle cx="${cx}" cy="${cy}" r="560" fill="url(#g)"/>`;
  for (let i = 0; i < 18; i++) {
    const r = 30 + i * 32 + i * i * 2.1;
    const o = Math.max(0.15, 1 - i / 18).toFixed(2);
    body += `<ellipse cx="${r1(cx + Math.sin(i * 0.6) * 6)}" cy="${r1(cy + Math.cos(i * 0.5) * 4)}" rx="${r1(r * 1.04)}" ry="${r1(r)}" fill="none" stroke="${c[1]}" stroke-opacity="${o}" stroke-width="${i % 4 === 3 ? 1.5 : 1}"/>`;
  }
  return cover(wall(lin('bg', [[0, c[0]], [1, c[2]]]) + glow('g', c[3]), body + `<circle cx="${cx}" cy="${cy}" r="4" fill="${c[1]}"/>`), c[0]);
}

function consoleSignal(c: Stops, seed: number): string {
  const rand = rng(seed);
  let body = '';
  for (let t = 0; t < 34; t++) {
    let x = -40 + rand() * 200;
    let y = 40 + t * 25 + rand() * 10;
    let d = `M${r1(x)} ${r1(y)}`;
    const end = 500 + rand() * 950;
    while (x < end) {
      x += 60 + rand() * 180;
      d += `H${r1(x)}`;
      if (rand() > 0.45) {
        x += 25;
        y += (rand() > 0.5 ? 1 : -1) * 25;
        d += `L${r1(x)} ${r1(y)}`;
      }
    }
    const hot = t % 6 === 2;
    const col = hot ? c[3] : c[1];
    body += `<path d="${d}" fill="none" stroke="${col}" stroke-width="${hot ? 1.6 : 1.2}" stroke-linejoin="round"/>`;
    body += `<circle cx="${r1(x)}" cy="${r1(y)}" r="${hot ? 3.2 : 2.4}" fill="${hot ? col : 'none'}" stroke="${col}" stroke-width="1.2"/>`;
  }
  return cover(wall(lin('bg', [[0, c[0]], [1, c[2]]], 0, 1), body), c[0]);
}

/** Dawn and Harvest: [sky x4, sun glow, sun disc, hill x4], hills from far to near. */
function consoleDawn(c: Stops): string {
  const sky = lin('bg', [[0, c[0]], [0.48, c[1]], [0.74, c[2]], [1, c[3]]], 0, 1);
  let body = `<ellipse cx="980" cy="560" rx="520" ry="300" fill="url(#sun)"/><circle cx="980" cy="550" r="48" fill="${c[5]}"/>`;
  c.slice(6, 10).forEach((fill, i) => {
    const base = 560 + i * 85;
    let d = `M0 ${CH}L0 ${base}`;
    for (let x = 0; x <= CW; x += 20) d += `L${x} ${r1(base - 40 * Math.sin(x / (260 + i * 70) + i * 1.7) - 22 * Math.sin(x / (110 + i * 30) + i))}`;
    body += `<path d="${d}L${CW} ${CH}Z" fill="${fill}"/>`;
  });
  return cover(wall(sky + glow('sun', c[4]!), body), c[0]);
}

function consoleMycelium(c: Stops, seed: number): string {
  const rand = rng(seed);
  let paths = '';
  let tips = '';
  const grow = (x: number, y: number, ang: number, len: number, depth: number): void => {
    if (depth > 7 || len < 10) {
      tips += `<circle cx="${r1(x)}" cy="${r1(y)}" r="2"/>`;
      return;
    }
    const nx = x + Math.cos(ang) * len;
    const ny = y + Math.sin(ang) * len;
    const qx = x + Math.cos(ang + 0.4) * len * 0.5;
    const qy = y + Math.sin(ang + 0.4) * len * 0.5;
    paths += `<path d="M${r1(x)} ${r1(y)}Q${r1(qx)} ${r1(qy)} ${r1(nx)} ${r1(ny)}" stroke-opacity="${(1 - depth * 0.083).toFixed(2)}" stroke-width="${(3.2 - depth * 0.35).toFixed(2)}"/>`;
    const n = rand() > 0.35 ? 2 : 1;
    for (let k = 0; k < n; k++) grow(nx, ny, ang + (rand() - 0.5) * 1.1, len * (0.68 + rand() * 0.2), depth + 1);
  };
  for (const [x, y, a] of [[180, 920, -1.35], [520, 930, -1.6], [880, 930, -1.45], [1180, 930, -1.8], [1380, 920, -2.1]] as const) grow(x, y, a, 190 + rand() * 60, 0);
  const body = `<circle cx="1050" cy="900" r="700" fill="url(#g)"/><g fill="none" stroke="${c[1]}" stroke-linecap="round">${paths}</g><g fill="${c[1]}">${tips}</g>`;
  return cover(wall(lin('bg', [[0, c[0]], [1, c[2]]], 0, 1) + glow('g', c[3]), body), c[0]);
}

/** Ember: [base, grid, horizon, glow, ember cell]. The design removed its rings and crosshair. */
function consoleEmber(c: Stops, seed: number): string {
  const rand = rng(seed);
  let grid = '';
  for (let x = 0; x <= CW; x += 60) grid += `M${x} 0V${CH}`;
  for (let y = 0; y <= CH; y += 60) grid += `M0 ${y}H${CW}`;
  let cells = '';
  for (let k = 0; k < 14; k++) cells += `<rect x="${Math.floor(rand() * 24) * 60}" y="${540 + Math.floor(rand() * 6) * 60}" width="60" height="60" fill-opacity="${(0.5 + rand() * 0.5).toFixed(2)}"/>`;
  const body = `<ellipse cx="720" cy="980" rx="1100" ry="360" fill="url(#g)"/><path d="${grid}" stroke="${c[1]}" stroke-width="1"/><g fill="${c[4]}">${cells}</g>`;
  return cover(wall(lin('bg', [[0, c[0]], [0.7, c[0]], [1, c[2]]], 0, 1) + glow('g', c[3]), body), c[0]);
}

function consoleLattice(c: Stops): string {
  let dots = '';
  for (let row = 0; row < 22; row++) {
    const t = row / 21;
    const y = 380 + Math.pow(t, 1.8) * 560;
    const gap = 18 + t * 46;
    for (let x = (row % 2) * (gap / 2); x < CW + gap; x += gap) dots += `<circle cx="${r1(x)}" cy="${r1(y)}" r="${(1 + t * 2).toFixed(2)}" fill-opacity="${(0.18 + t * 0.82).toFixed(2)}"/>`;
  }
  const body =
    `<g fill="${c[1]}">${dots}</g>` +
    `<path d="M120 900 C 420 640, 700 600, 980 520 S 1300 430, 1440 400" fill="none" stroke="${c[1]}" stroke-width="1.6"/>` +
    `<path d="M0 760 C 360 700, 760 690, 1440 600" fill="none" stroke="${c[1]}" stroke-opacity="0.4" stroke-width="1.2"/>` +
    `<circle cx="980" cy="520" r="5" fill="${c[3]}"/><circle cx="980" cy="520" r="14" fill="none" stroke="${c[3]}" stroke-opacity="0.5"/>`;
  return cover(wall(lin('bg', [[0, c[0]], [1, c[2]]], 0, 1), body), c[0]);
}

export const WALLPAPERS: Record<WallpaperId, Wallpaper> = {
  onemind: {
    id: 'onemind',
    name: 'OneMind',
    kind: 'mesh',
    accent: 'onemind',
    colors: { light: ['#f8f4f3', '#f3c9cc', '#e8e1ef', '#efe2db'], dark: ['#09090c', '#5c0f18', '#1c1029', '#2a1a1f'] },
    render: (c) =>
      `${neural(c, 1)} center / cover no-repeat, ${radial('12%', '8%', c[1], '58%')}, ${radial('92%', '96%', c[2], '62%')}, ${radial('80%', '18%', c[3], '45%')}, ${c[0]}`,
  },
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
    accent: 'teal',
    colors: { light: ['#f1f3f2', '#d9dddd', '#e6ebe9', '#f79d9f'], dark: ['#0b0f13', '#1f262a', '#0e1418', '#681d22'] },
    render: (c) => consoleContour(c),
  },
  ripple: {
    id: 'ripple',
    name: 'Ripple',
    kind: 'pattern',
    accent: 'graphite',
    colors: { light: ['#f7f6f4', '#c5c3c2', '#eae6e2', '#dbdde2'], dark: ['#0a0b0e', '#39393d', '#121015', '#21252e'] },
    render: (c) => consoleRipple(c),
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
    accent: 'onemind',
    colors: { light: ['#f7f7f8', '#e3e3e4', '#ececef', '#fc8186'], dark: ['#09090b', '#1b1b1d', '#121216', '#902025'] },
    render: (c) => consoleSignal(c, 21),
  },
  dawn: {
    id: 'dawn',
    name: 'Dawn',
    kind: 'landscape',
    accent: 'rose',
    colors: {
      light: ['#fbf1ee', '#f8dcd6', '#f2bdb4', '#eba8a2', '#fef0e1', '#fff8ee', '#e7b2ab', '#d4968f', '#b67b79', '#8e5e62'],
      dark: ['#0c0a18', '#22122a', '#5e1c2a', '#2a0f18', '#b73534', '#db5045', '#2a1220', '#1c0e18', '#130a12', '#0b070c'],
    },
    render: (c) => consoleDawn(c),
  },
  harvest: {
    id: 'harvest',
    name: 'Harvest',
    kind: 'landscape',
    accent: 'copper',
    colors: {
      light: ['#fff3e4', '#fbddc0', '#f5be98', '#efa986', '#fef0de', '#fff8ee', '#e9b48f', '#d99878', '#bd7c62', '#93604e'],
      dark: ['#120c08', '#2a1a0e', '#6a3414', '#2a140a', '#bc632b', '#de6740', '#2e1a0e', '#211309', '#170d07', '#0d0805'],
    },
    render: (c) => consoleDawn(c),
  },
  mycelium: {
    id: 'mycelium',
    name: 'Mycelium',
    kind: 'pattern',
    accent: 'moss',
    colors: { light: ['#f4f8f1', '#95b7a0', '#e3eedf', '#c3e2c4'], dark: ['#0a110d', '#436b4f', '#12201a', '#193a29'] },
    render: (c) => consoleMycelium(c, 5),
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
    colors: { light: ['#fafafa', '#6a6a6a', '#ececec', '#ff333a'], dark: ['#050506', '#939394', '#101012', '#ff333a'] },
    render: (c) => consoleLattice(c),
  },
  ember: {
    id: 'ember',
    name: 'Ember',
    kind: 'pattern',
    accent: 'onemind',
    colors: { light: ['#fbf6f2', '#f1dad5', '#f1dcd3', '#f3c2b9', '#ebc8c0'], dark: ['#050404', '#1b0a09', '#1a0706', '#5f1713', '#310d0b'] },
    render: (c) => consoleEmber(c, 9),
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
 * The smallest dim (0..1, in steps of 0.05) at which body text, muted text and the accent
 * all reach 4.5:1 on every painted colour once the theme-coloured veil is laid over it.
 * Dimming blends the wallpaper towards the page background, so light themes "fade" it and
 * dark themes "darken" it. A dim of 1 covers the wallpaper with the page background: the last
 * resort when nothing less keeps text readable (every accent passes AA on the background itself).
 */
export function minDim(stops: readonly string[] | null, theme: ThemeName, accent?: string): number {
  if (!stops || stops.length === 0) return UNKNOWN_IMAGE_MIN_DIM;
  const colors = paintedColors(stops);
  const fg = accent ? [...TEXT[theme], accent] : TEXT[theme];
  for (let step = 0; step <= 20; step++) {
    const d = step * 0.05;
    const ok = colors.every((c) => {
      const under = mix(VEIL[theme], c, d);
      return fg.every((f) => contrast(f, under) >= AA);
    });
    if (ok) return Math.round(d * 100) / 100;
  }
  return 1;
}

export function wallpaperBackground(id: WallpaperId, theme: ThemeName): string {
  const w = WALLPAPERS[id];
  return w.render(w.colors[theme]);
}

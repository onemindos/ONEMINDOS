// SPDX-License-Identifier: Apache-2.0
// Colour maths for the customization engine: parsing, WCAG contrast, OKLCH lightness
// adjustment and alpha blending. Written for OneMind from the public formulas:
// WCAG 2.2 relative luminance (https://www.w3.org/TR/WCAG22/#dfn-relative-luminance) and
// OKLab (Björn Ottosson, 2020, public-domain matrices). No third-party code.

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** True for `#rgb` or `#rrggbb` (the `#` is optional). */
export function isHex(value: string): boolean {
  return HEX.test(value.trim());
}

/** Normalise to lower-case `#rrggbb`, or null when the text is not a hex colour. */
export function normalizeHex(value: string): string | null {
  const m = HEX.exec(value.trim());
  if (!m) return null;
  let h = m[1]!.toLowerCase();
  if (h.length === 3) h = h.replace(/./g, (c) => c + c);
  return `#${h}`;
}

export function hexToRgb(hex: string): Rgb {
  const n = normalizeHex(hex);
  if (!n) throw new Error(`not a hex colour: ${hex}`);
  return { r: parseInt(n.slice(1, 3), 16), g: parseInt(n.slice(3, 5), 16), b: parseInt(n.slice(5, 7), 16) };
}

const clamp255 = (v: number) => Math.min(255, Math.max(0, Math.round(v)));

export function rgbToHex({ r, g, b }: Rgb): string {
  return `#${[r, g, b].map((v) => clamp255(v).toString(16).padStart(2, '0')).join('')}`;
}

/** Linear sRGB channel (0..1) from an 8-bit value. */
function lin(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}
function unlin(c: number): number {
  const s = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
  return s * 255;
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function luminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio between two colours, 1 to 21. */
export function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Blend `top` over `bottom` with `alpha` (0..1) of `top`, in sRGB as browsers composite. */
export function mix(top: string, bottom: string, alpha: number): string {
  const t = hexToRgb(top);
  const u = hexToRgb(bottom);
  const a = Math.min(1, Math.max(0, alpha));
  return rgbToHex({ r: t.r * a + u.r * (1 - a), g: t.g * a + u.g * (1 - a), b: t.b * a + u.b * (1 - a) });
}

export interface Oklch {
  l: number;
  c: number;
  h: number;
}

export function hexToOklch(hex: string): Oklch {
  const { r, g, b } = hexToRgb(hex);
  const [R, G, B] = [lin(r), lin(g), lin(b)];
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const Bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const c = Math.sqrt(A * A + Bb * Bb);
  const h = ((Math.atan2(Bb, A) * 180) / Math.PI + 360) % 360;
  return { l: L, c, h };
}

function oklchToLinear({ l: L, c, h }: Oklch): [number, number, number] {
  const hr = (h * Math.PI) / 180;
  const A = c * Math.cos(hr);
  const B = c * Math.sin(hr);
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

/** OKLCH to hex. Out-of-gamut colours keep hue and lightness and lose chroma until they fit. */
export function oklchToHex(o: Oklch): string {
  let c = o.c;
  for (let i = 0; i < 40; i++) {
    const rgb = oklchToLinear({ ...o, c });
    if (rgb.every((v) => v >= -0.0005 && v <= 1.0005)) {
      return rgbToHex({ r: unlin(Math.max(0, rgb[0])), g: unlin(Math.max(0, rgb[1])), b: unlin(Math.max(0, rgb[2])) });
    }
    c *= 0.9;
  }
  const grey = oklchToLinear({ ...o, c: 0 });
  return rgbToHex({ r: unlin(grey[0]), g: unlin(grey[1]), b: unlin(grey[2]) });
}

/** Same hue and chroma, new OKLCH lightness (0..1). */
export function withLightness(hex: string, l: number): string {
  const o = hexToOklch(hex);
  return oklchToHex({ ...o, l: Math.min(1, Math.max(0, l)) });
}

/** Mean colour of a list (used for a wallpaper's tint). */
export function average(hexes: readonly string[]): string {
  const sum = hexes.map(hexToRgb).reduce((a, c) => ({ r: a.r + c.r, g: a.g + c.g, b: a.b + c.b }), { r: 0, g: 0, b: 0 });
  const n = Math.max(1, hexes.length);
  return rgbToHex({ r: sum.r / n, g: sum.g / n, b: sum.b / n });
}

// SPDX-License-Identifier: Apache-2.0
// Fonts are self-hosted (no font CDN call), open-licence, and numbers use tabular figures.
import { describe, expect, it } from 'vitest';
import fontsCss from './fonts.css?raw';
import baseCss from './base.css?raw';
import licence from './fonts/OFL.txt?raw';
import tokensCss from '../tokens/tokens.css?raw';

const files = import.meta.glob('./fonts/*.woff2', { eager: true, query: '?url' });

describe('self-hosted type', () => {
  it('ships one subsetted woff2 with its licence, and loads only that file', () => {
    expect(Object.keys(files)).toEqual(['./fonts/inter-latin-wght.woff2']);
    expect(licence).toContain('SIL OPEN FONT LICENSE Version 1.1');
    const urls = [...fontsCss.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1]!.replace(/['"]/g, ''));
    expect(urls.length).toBeGreaterThan(0);
    for (const u of urls) expect(u).toBe('./fonts/inter-latin-wght.woff2');
  });

  it('never points at a font service', () => {
    for (const css of [fontsCss, baseCss, tokensCss]) expect(css).not.toMatch(/https?:\/\/|googleapis|gstatic|typekit|fonts\.bunny/i);
    expect(fontsCss).toContain('font-display: swap');
  });

  it('puts the font first in the stack, with the system font as fallback', () => {
    expect(tokensCss).toMatch(/--om-font-sans: 'Inter Variable', system-ui/);
  });

  it('gives clocks, counts, metrics and table cells tabular figures', () => {
    const rule = baseCss.slice(baseCss.indexOf('Numbers that change'));
    for (const sel of ['time', 'td', 'dd', "[class*='-count']", "[class*='-stat']", "[class*='-metric']"]) expect(rule).toContain(sel);
    expect(rule).toContain('font-variant-numeric: tabular-nums');
  });
});

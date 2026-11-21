// SPDX-License-Identifier: Apache-2.0
// Motion and icons of the desktop frame: durations come from tokens, demo apps carry icons.
import { describe, expect, it } from 'vitest';
import css from './shell/desktop.css?raw';
import { makeApps } from './api/fixtures';

const drawn = import.meta.glob('../public/mock-icons/*.svg', { eager: true, query: '?url' });
describe('desktop motion', () => {
  it('has no hard-coded durations: every animation and transition uses the motion tokens', () => {
    expect(css).not.toMatch(/\b\d+(\.\d+)?m?s\b(?!\))/);
    expect(css).toContain('var(--om-motion-duration-base)');
    expect(css).toContain('var(--om-motion-ease-standard)');
    for (const name of ['dsk-open', 'dsk-fade', 'dsk-pop', 'dsk-zoom']) expect(css).toMatch(new RegExp(`animation: ${name} var\\(--dsk-t-`));
  });

  it('still switches animations off for reduced motion', () => {
    expect(css).toMatch(/prefers-reduced-motion: reduce[\s\S]*animation: none/);
  });
});

describe('demo catalog icons', () => {
  it('gives every demo app its own icon path (the monogram is only a fallback)', () => {
    const apps = makeApps();
    expect(apps.length).toBeGreaterThan(5);
    for (const a of apps) {
      expect(a.icon).toBe(`/mock-icons/${a.id}.svg`);
      expect(Object.keys(drawn)).toContain(`../public/mock-icons/${a.id}.svg`);
    }
  });
});

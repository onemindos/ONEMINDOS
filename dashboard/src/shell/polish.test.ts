// SPDX-License-Identifier: Apache-2.0
// The polish rules that cannot be seen in jsdom (no layout): they live in CSS, so the test reads the CSS.
// What each one protects is written beside it. Real layout is checked in the screenshot pass.
import { describe, expect, it } from 'vitest';

// vitest runs with css:false (a CSS import would be empty), so read the files from disk. The specifier is built at
// run time because the dashboard carries no Node type definitions.
const { readFileSync } = (await import(/* @vite-ignore */ ['node', 'fs'].join(':'))) as { readFileSync: (u: URL, enc: 'utf8') => string };
const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8');
const desktop = read('./desktop.css');
const base = read('../../../ui/src/styles/base.css');
const components = read('../../../ui/src/styles/components.css');
const phone = desktop.slice(desktop.lastIndexOf('@media (max-width: 720px)'));

describe('accessibility rules in CSS', () => {
  it('sets a placeholder colour (the browser default is about 3.8:1 in dark)', () => {
    expect(base).toMatch(/::placeholder\s*\{[^}]*color:\s*var\(--om-color-text-muted\)/);
  });
  it('stops the live-dot pulse and the job spinner under prefers-reduced-motion', () => {
    expect(components).toMatch(/prefers-reduced-motion: reduce\) \{ \.om-pulse \{ animation: none/);
    expect(components).toMatch(/prefers-reduced-motion: reduce\) \{ \.om-glyph-spin \{ animation: none/);
  });
  it('keeps panes at least 84% opaque and has prefers-contrast and forced-colors rules', () => {
    expect(desktop).toMatch(/--dsk-pane-min:\s*84%/);
    expect(desktop).toMatch(/@media \(prefers-contrast: more\)/);
    expect(desktop).toMatch(/@media \(forced-colors: active\)/);
  });
  it('leaves room under the dock when a row takes focus', () => {
    expect(desktop).toMatch(/html \{ scroll-padding-bottom: calc\(var\(--dsk-dock-h/);
  });
  it('centres the dock without left:50% (that form made it wider than a phone)', () => {
    expect(desktop).toMatch(/\.dsk-dock \{ left: 0; right: 0; transform: none; margin-inline: auto; width: fit-content/);
  });
});

describe('phone layout in CSS', () => {
  it('makes the menu-bar, window and tab targets 44 px and the avatar 36 px', () => {
    expect(phone).toMatch(/\.dsk-iconbtn \{ width: 44px; height: 44px; \}/);
    expect(phone).toMatch(/\.dsk-wbtn \{ width: 44px; height: 44px; \}/);
    expect(phone).toMatch(/\.dsk-avatar \{ width: 36px; height: 36px;/);
    expect(phone).toMatch(/\.dash-tabs a \{ min-height: 44px; \}/);
  });
  it('shows the dock labels at 12 px on phones instead of hiding them', () => {
    expect(phone).toMatch(/\.dsk-dock-item \{ width: 58px;/);
    expect(desktop).not.toMatch(/aria-current='page'\] \.dsk-dock-label \{[^}]*font-weight/);
    expect(phone).toMatch(/\.dsk-dock-label \{ position: static;[^}]*font-size: 12px/);
  });
  it('the shared chip, icon button and small button are 44 px on phones', () => {
    expect(components).toMatch(/max-width: 720px\) \{\s*\.om-icon-btn, \.om-btn-sm, \.om-set-chip[^{]*\{ min-height: var\(--om-layout-touch-target\)/);
  });
});

describe('one main-button colour, and an opaque launchpad', () => {
  it('the primary button is neutral ink, never the red accent or the danger colour (Approve is never red)', () => {
    const rule = components.match(/\.om-btn-primary \{[^}]*\}/)?.[0] ?? '';
    expect(rule).toMatch(/background: var\(--om-color-text\)/);
    expect(rule).not.toMatch(/accent|danger/);
  });
  it('the launchpad scrim is at least 92 percent opaque, hides the dock and clears the safe area', () => {
    const pct = Number(desktop.match(/\.dsk-launchpad \{ background: color-mix\(in srgb, var\(--om-color-bg\) (\d+)%/)?.[1]);
    expect(pct).toBeGreaterThanOrEqual(92);
    expect(desktop).toMatch(/\.dsk:has\(\.dsk-launchpad\) \.dsk-dock \{ visibility: hidden/);
    expect(desktop).toMatch(/\.dsk-launchpad-inner \{ padding-bottom: calc\(120px \+ env\(safe-area-inset-bottom/);
  });
});

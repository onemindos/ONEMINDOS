// SPDX-License-Identifier: Apache-2.0
// The jobs pill (dashboard shell, ActionJobs) must never cover content or a control. The CSS lives in the dashboard
// package, but only this package's tests can read files with node:fs, so the rule is pinned here.
// @ts-expect-error -- Node built-in; this package has no @types/node. Tests run in Node.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

declare const process: { cwd(): string };
const desktopCss: string = readFileSync(`${process.cwd()}/../dashboard/src/shell/desktop.css`, 'utf8');

describe('desktop shell jobs pill placement', () => {
  it('wide screens put the pill on the dock row; narrower ones stack it above the dock and reserve its room', () => {
    const rule = /\.dash-desktop \.om-store-tray \{[^}]*\}/.exec(desktopCss)?.[0] ?? '';
    expect(rule).toContain('right: var(--om-space-4)');
    expect(rule).toContain('var(--dsk-dock-bottom)');
    expect(desktopCss).toMatch(/@media \(min-width: 1025px\) \{\s*\.dash-desktop\[data-jobs\] \.dsk-dock \{ max-width: calc\(100vw - 2 \*/);
    const stacked = desktopCss.slice(desktopCss.indexOf('@media (max-width: 1024px) {\n  .dash-desktop .om-store-tray'));
    expect(stacked).toContain('var(--dsk-dock-box) + var(--dsk-pill-gap)');
    expect(stacked).toContain('--dsk-jobs-reserve: var(--dsk-jobs-stack, 0px)');
    // Home's scroll region and every window end above the pill; with no job the variable falls back to 0px.
    expect(desktopCss.match(/var\(--dsk-jobs-reserve, 0px\)/g)).toHaveLength(3); // Home scroll region, the stage, and the phone stage override
  });
});

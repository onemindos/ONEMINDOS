// SPDX-License-Identifier: Apache-2.0
// The shell draws the jobs tray (ActionJobs) on every screen, with classes from ui/src/store/store.css. Screens now load
// lazily, so those styles must not depend on a screen having imported them (they once arrived only with the Market
// screen: the tray then sat in normal flow at the page bottom, unstyled, until Market was opened).
import uiEntry from '../../../ui/src/index.ts?raw';
import actionJobs from './ActionJobs.tsx?raw';
import shellSrc from './Shell.tsx?raw';
import { jobsStackStyle, pillLabel, JOBS_STACK } from './ActionJobs';

describe('shell styles do not depend on a lazy screen', () => {
  it('the ui entry imports store.css directly (a .ts barrel import is dropped when unused)', () => {
    expect(uiEntry).toMatch(/^import '\.\/store\/store\.css';$/m);
  });

  it('every class ActionJobs renders for the tray exists in the ui store styles it relies on', () => {
    for (const cls of ['om-store-tray', 'om-store-tray-pill', 'om-store-tray-panel']) expect(actionJobs).toContain(cls);
    // position: fixed on Home is asserted in the browser (ui/test/e2e/flows.spec.ts): vitest does not process CSS.
  });
});

describe('the jobs pill never covers content (shell rule, every screen)', () => {
  it('the shell sets the reserve variable only while a job exists', () => {
    expect(jobsStackStyle(false)).toBeUndefined();
    expect(jobsStackStyle(true)).toEqual({ '--dsk-jobs-stack': JOBS_STACK });
    expect(shellSrc).toContain('style={jobsStackStyle(jobsShown)}');
    expect(shellSrc).toContain('<ActionJobs onShown={setJobsShown} />');
  });

  it('the label is short (count plus state) and the full text is the accessible name', () => {
    expect(pillLabel(1, { state: 'awaiting_approval' })).toBe('1 job waiting');
    expect(pillLabel(3, { state: 'dispatched' })).toBe('3 jobs running');
    expect(pillLabel(0, { state: 'succeeded' })).toBe('Jobs done');
    expect(actionJobs).toMatch(/aria-label=\{`\$\{pillLabel\(/);
    expect(actionJobs).not.toContain('text-overflow');
  });
});

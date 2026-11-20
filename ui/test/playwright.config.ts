// SPDX-License-Identifier: Apache-2.0
// Real-browser checks for the ui/ demo and the dashboard mock build (docs/testing/CI-MATRIX.md).
// Projects: chromium, firefox, webkit. CI runs one project per job (.github/workflows/ui-quality.yml).
import { defineConfig, devices, type ReporterDescription } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));
const UI_DIST = process.env.UI_DIST ?? here('../dist-demo');
const DASH_DIST = process.env.DASH_DIST ?? here('../../dashboard/dist');
// Where the reference screenshots live. Nothing is committed: CI renders them from the PR's base
// (main) in the same job, and visual-vs-main.sh does the same on a developer machine (README.md).
const VISUAL_DIR = process.env.VISUAL_DIR ?? here('./visual');
// One run of axe and flows and one visual run share a job, so each run can get its own report.
const REPORT_DIR = process.env.PW_REPORT ?? 'playwright-report';
const JSON_OUT = process.env.PW_JSON; // machine-readable results, read by scripts/ui-visual-verdict.py
const UI_URL = 'http://127.0.0.1:4173/'; // e2e/screens.ts uses the same ports
const DASH_URL = 'http://127.0.0.1:4174/';
const CI = !!process.env.CI;

// Desktop baseline: 1280 x 860 at scale 1 (the size the design screenshots use).
const desktop = { viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 };

export default defineConfig({
  testDir: './e2e',
  // One reference set per engine under <VISUAL_DIR>/<browser>/ (no OS suffix: CI is Linux only).
  snapshotPathTemplate: `${VISUAL_DIR}/{projectName}/{arg}{ext}`,
  outputDir: process.env.PW_OUTPUT ?? './test-results',
  fullyParallel: true,
  forbidOnly: CI,
  retries: 0, // a flaky check is a bug to fix, not to retry
  workers: CI ? 4 : undefined,
  timeout: 60_000,
  reporter: [
    ['list'],
    // The visual run sets PW_GITHUB=0: a difference is a verdict for the gate, not a code annotation.
    ...(CI && process.env.PW_GITHUB !== '0' ? [['github'] as ReporterDescription] : []),
    ['html', { open: 'never', outputFolder: REPORT_DIR }],
    ...(JSON_OUT ? [['json', { outputFile: JSON_OUT }] as ReporterDescription] : []),
  ],
  expect: {
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
      // Same engine, same runner image: renders are near-identical. 0.1% of the pixels absorbs
      // anti-aliasing noise; a changed word, colour or spacing is far larger.
      maxDiffPixelRatio: 0.001,
    },
  },
  use: {
    locale: 'en-US',
    timezoneId: 'UTC',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], ...desktop } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'], ...desktop } },
    { name: 'webkit', use: { ...devices['Desktop Safari'], ...desktop } },
  ],
  webServer: [
    { command: `node serve.mjs "${UI_DIST}" 4173`, url: UI_URL, reuseExistingServer: !CI, timeout: 30_000 },
    { command: `node serve.mjs "${DASH_DIST}" 4174`, url: DASH_URL, reuseExistingServer: !CI, timeout: 30_000 },
  ],
});

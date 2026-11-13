// SPDX-License-Identifier: Apache-2.0
// Real-browser checks for the ui/ demo and the dashboard mock build (docs/testing/CI-MATRIX.md).
// Projects: chromium, firefox, webkit. CI runs one project per job (.github/workflows/ui-quality.yml).
import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));
const UI_DIST = process.env.UI_DIST ?? here('../dist-demo');
const DASH_DIST = process.env.DASH_DIST ?? here('../../dashboard/dist');
const UI_URL = 'http://127.0.0.1:4173/'; // e2e/screens.ts uses the same ports
const DASH_URL = 'http://127.0.0.1:4174/';
const CI = !!process.env.CI;

// Desktop baseline: 1280 x 860 at scale 1 (the size the design screenshots use).
const desktop = { viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 };

export default defineConfig({
  testDir: './e2e',
  // One baseline per engine, committed under ui/test/visual/<browser>/ (no OS suffix: CI is Linux only).
  snapshotPathTemplate: '{testDir}/../visual/{projectName}/{arg}{ext}',
  outputDir: './test-results',
  fullyParallel: true,
  forbidOnly: CI,
  retries: 0, // a flaky check is a bug to fix, not to retry
  workers: CI ? 4 : undefined,
  timeout: 60_000,
  reporter: CI
    ? [['list'], ['github'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
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

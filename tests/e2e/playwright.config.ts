// SPDX-License-Identifier: Apache-2.0
import { defineConfig, devices } from '@playwright/test';

const out = process.env.E2E_OUT ?? 'out';

export default defineConfig({
  // The golden path is one story against one hub: run it in order, one worker.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  outputDir: `${out}/test-results`,
  reporter: [
    ['list'],
    ['html', { outputFolder: `${out}/playwright-report`, open: 'never' }],
    ['junit', { outputFile: `${out}/junit.xml` }],
  ],
  projects: [
    { name: 'unit', testDir: 'unit' },
    {
      name: 'golden',
      testDir: 'specs',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.E2E_HUB_URL,
        // The browser trusts the box CA by its public key only (E2E_CHROMIUM_ARGS from the harness: a pin on the
        // CA's SPKI, plus the name mapping the forwarded port needs); verification itself stays on.
        launchOptions: { args: process.env.E2E_CHROMIUM_ARGS ? JSON.parse(process.env.E2E_CHROMIUM_ARGS) : [] },
        screenshot: 'on',
        video: 'on',
        // A trace holds every request's Authorization header and every evaluate argument (the owner
        // token). CI uploads out/, so traces are local-only unless E2E_TRACE=1 asks for them.
        trace: process.env.CI && process.env.E2E_TRACE !== '1' ? 'off' : 'retain-on-failure',
        actionTimeout: 30_000,
      },
    },
  ],
});

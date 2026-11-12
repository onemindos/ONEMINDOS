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
        screenshot: 'on',
        video: 'on',
        trace: 'retain-on-failure',
        actionTimeout: 30_000,
      },
    },
  ],
});

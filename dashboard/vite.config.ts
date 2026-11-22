// SPDX-License-Identifier: Apache-2.0
/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// @onemind/ui is consumed from source (../ui/src), so the dashboard needs no ui build step and
// ui/ needs no npm install of its own. React is resolved once, from dashboard/node_modules.
const uiSrc = decodeURIComponent(new URL('../ui/src', import.meta.url).pathname);
const sdkSrc = decodeURIComponent(new URL('../sdk/ts/src', import.meta.url).pathname);
const openapiDir = decodeURIComponent(new URL('../sdk/openapi', import.meta.url).pathname); // read by the CI-08 drift test

// The gateway (core/) serves dist/ at "/" with SPA fallback (contract §3 "Static").
// In dev, /v1 and /healthz are proxied to a local gateway on :8080 (contract §1).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [{ find: /^@onemind\/ui$/, replacement: `${uiSrc}/index.ts` }, { find: /^@onemind\/sdk$/, replacement: `${sdkSrc}/index.ts` }],
    dedupe: ['react', 'react-dom', 'uqr'],
  },
  build: { outDir: 'dist', sourcemap: false },
  server: {
    fs: { allow: ['.', uiSrc, sdkSrc, openapiDir] },
    proxy: {
      '/v1': 'http://localhost:8080',
      '/healthz': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // 5 s is vitest's default. The userEvent suites (locale, Control Hub secrets, screens, Usage, Agent stop, the
    // app store depth, Files) take 1.2 to 2.1 s on an idle 4-CPU machine and past 5 s when other test files share
    // it, while they pass on 16 CPUs. A timeout only decides when a hung test is given up: 15 s still catches a
    // hang. No test is skipped. (A few tests set their own, longer limit and keep it.)
    testTimeout: 15_000,
    hookTimeout: 15_000,
    setupFiles: ['./src/test/setup.ts'],
    // Styles are skipped, except the desktop frame's, which polish.test.ts reads with ?raw.
    css: { include: [/shell\/desktop\.css/] },
  },
});

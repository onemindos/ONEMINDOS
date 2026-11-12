// SPDX-License-Identifier: Apache-2.0
/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// @onemind/ui is consumed from source (../ui/src), so the dashboard needs no ui build step and
// ui/ needs no npm install of its own. React is resolved once, from dashboard/node_modules.
const uiSrc = decodeURIComponent(new URL('../ui/src', import.meta.url).pathname);

// The gateway (core/) serves dist/ at "/" with SPA fallback (contract §3 "Static").
// In dev, /v1 and /healthz are proxied to a local gateway on :8080 (contract §1).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [{ find: /^@onemind\/ui$/, replacement: `${uiSrc}/index.ts` }],
    dedupe: ['react', 'react-dom'],
  },
  build: { outDir: 'dist', sourcemap: false },
  server: {
    fs: { allow: ['.', uiSrc] },
    proxy: {
      '/v1': 'http://localhost:8080',
      '/healthz': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});

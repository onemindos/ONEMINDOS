// SPDX-License-Identifier: Apache-2.0
/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Library build: dist/onemind-ui.js (ES module) + dist/ui.css (tokens and component styles).
// React is a peer dependency and is never bundled.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'src/index.ts',
      formats: ['es'],
      fileName: () => 'onemind-ui.js',
      cssFileName: 'ui',
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime'],
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // 5 s is vitest's default. The userEvent suites (Home editing, Onboarding by keyboard, Appearance, the Market)
    // take 1.4 to 2.4 s on an idle 4-CPU machine and past 5 s when other test files share it, while they pass on
    // 16 CPUs. A timeout only decides when a hung test is given up: 15 s still catches a hang. No test is skipped.
    testTimeout: 15_000,
    hookTimeout: 15_000,
    setupFiles: ['./src/test/setup.ts'],
    // Only these stylesheets are processed, so tests can read them with ?raw.
    css: { include: [/tokens\.css/, /styles\/(fonts|base)\.css/] },
    include: ['src/**/*.test.{ts,tsx}', 'demo/src/**/*.test.{ts,tsx}'],
  },
});

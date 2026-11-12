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
    setupFiles: ['./src/test/setup.ts'],
    // Only tokens.css is processed, so the drift test can read it with ?raw.
    css: { include: [/tokens\.css/] },
    include: ['src/**/*.test.{ts,tsx}', 'demo/src/**/*.test.{ts,tsx}'],
  },
});

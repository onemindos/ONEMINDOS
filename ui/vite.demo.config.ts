// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Static screen mocks for every IA screen (docs/design/IA.md), fed by fixtures only.
// No network calls: the demo never talks to a gateway.
export default defineConfig({
  root: 'demo',
  base: './',
  plugins: [react()],
  build: { outDir: '../dist-demo', emptyOutDir: true, sourcemap: false },
});

// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { THREE_MARKER, checkBundle } from './bundle-check.mjs';

const THREE = `window.${THREE_MARKER}="187";`;
const html = '<!doctype html><script type="module" crossorigin src="/assets/index-a.js"></script><link rel="modulepreload" crossorigin href="/assets/vendor-b.js">';

it('passes when three.js is only in a chunk loaded by a dynamic import', () => {
  const result = checkBundle({
    'index.html': html,
    'assets/index-a.js': 'import{r as e}from"./vendor-b.js";import"./shared-c.js";const s=()=>import("./Engine-d.js");',
    'assets/vendor-b.js': 'export const r=1;',
    'assets/shared-c.js': 'export{}',
    'assets/Engine-d.js': `import{r}from"./vendor-b.js";${THREE}`,
  });
  expect(result).toEqual({ eager: ['assets/index-a.js', 'assets/shared-c.js', 'assets/vendor-b.js'], three: ['assets/Engine-d.js'], problems: [] });
});

it('fails when an eager chunk statically imports a chunk carrying three.js', () => {
  const { problems } = checkBundle({
    'index.html': html,
    'assets/index-a.js': 'import{x}from"./three-e.js";',
    'assets/vendor-b.js': 'export{}',
    'assets/three-e.js': THREE,
  });
  expect(problems).toEqual(['three.js is in assets/three-e.js, which every page loads: import it only from the lazy /spatial engine']);
});

it('fails when three.js is in the entry itself or in a preloaded chunk', () => {
  const entry = checkBundle({ 'index.html': html, 'assets/index-a.js': THREE, 'assets/vendor-b.js': '' });
  expect(entry.problems).toHaveLength(1);
  const preload = checkBundle({ 'index.html': html, 'assets/index-a.js': '', 'assets/vendor-b.js': THREE });
  expect(preload.problems).toEqual(['three.js is in assets/vendor-b.js, which every page loads: import it only from the lazy /spatial engine']);
});

it('never passes empty: no build, no entry or no three.js at all is a failure', () => {
  expect(checkBundle({}).problems).toEqual(['index.html is missing: run vite build first']);
  expect(checkBundle({ 'index.html': '<p>', 'assets/x.js': THREE }).problems).toEqual(['index.html names no module script']);
  expect(checkBundle({ 'index.html': html, 'assets/index-a.js': '', 'assets/vendor-b.js': '' }).problems)
    .toEqual(['no chunk carries three.js: the spatial engine is missing from the build']);
});

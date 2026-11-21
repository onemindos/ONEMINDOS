// SPDX-License-Identifier: Apache-2.0
import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

// Screens load lazily (screens/registry), so the first render of a screen waits on a dynamic import; the 1s default is too tight on a busy runner.
configure({ asyncUtilTimeout: 5000 });

beforeEach(() => {
  window.sessionStorage.clear();
  // Per-person preferences must not leak between tests. Node 25+ shadows jsdom's localStorage with
  // its own, which is undefined without --localstorage-file; CI (Node 22) has jsdom's.
  window.localStorage?.clear();
});
afterEach(() => {
  cleanup();
});

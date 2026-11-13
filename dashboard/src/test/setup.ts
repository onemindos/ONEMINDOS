// SPDX-License-Identifier: Apache-2.0
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

beforeEach(() => {
  window.sessionStorage.clear();
  // Per-person preferences must not leak between tests. Node 25+ shadows jsdom's localStorage with
  // its own, which is undefined without --localstorage-file; CI (Node 22) has jsdom's.
  window.localStorage?.clear();
});
afterEach(() => {
  cleanup();
});

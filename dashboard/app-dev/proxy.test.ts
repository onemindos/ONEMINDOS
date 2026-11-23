// SPDX-License-Identifier: Apache-2.0
// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

it('sends both dev proxies only to the loopback gateway chosen by app dev', async () => {
  vi.stubEnv('ONEMIND_PORT', '31827');
  const { default: config } = await import('./vite.config');
  for (const prefix of ['/v1', '/healthz']) {
    const proxy = config.server?.proxy?.[prefix];
    expect(typeof proxy === 'string' ? proxy : proxy?.target).toBe('http://127.0.0.1:31827');
  }
});

it('rejects an invalid gateway port before starting Vite', async () => {
  vi.stubEnv('ONEMIND_PORT', '70000');
  await expect(import('./vite.config')).rejects.toThrow('Invalid local gateway port');
});

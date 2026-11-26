// SPDX-License-Identifier: Apache-2.0
// The demo catalogue carries each app's real licence class (#867 shows only green classes by default).
import { describe, expect, it } from 'vitest';
import { DEFAULT_FILTERS } from '@onemind/ui';
import { toStoreApp } from '../data/adapters';
import { makeApps } from './fixtures';

const { readFileSync } = (await import(/* @vite-ignore */ ['node', 'fs'].join(':'))) as { readFileSync: (u: URL, enc: 'utf8') => string };
// A variable path keeps Vite from turning the read into an asset import.
const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8');

describe('demo catalogue licence classes', () => {
  it('match metadata.licenceClass in each app manifest under apps/', () => {
    for (const app of makeApps()) {
      const manifest = read(['..', '..', '..', 'apps', app.id, 'onemind.app.yaml'].join('/'));
      const declared = /^\s*licenceClass:\s*["']?([A-Za-z0-9]+)/m.exec(manifest)?.[1];
      expect(declared, app.id).toBeDefined();
      expect(app.licence_class, app.id).toBe(declared);
    }
  });

  it('leave apps in the Market under the default green-licence filter, and label Uptime Kuma permissive', () => {
    const cards = makeApps().map(toStoreApp);
    const green = cards.filter((c) => DEFAULT_FILTERS.licences.includes(c.licence_class ?? 'L?'));
    expect(green.length).toBeGreaterThan(0);
    expect(cards.find((c) => c.id === 'uptime-kuma')?.licence_class).toBe('L1');
    // A manifest that declares no class stays unclear (never shown as green): Chromium today.
    expect(cards.find((c) => c.id === 'chromium')?.licence_class).toBe('L?');
  });
});

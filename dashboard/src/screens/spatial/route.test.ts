// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { SCREENS } from '../registry';

it('mounts the diagnostics link target in the dashboard', () => {
  expect(SCREENS.find(s => s.path === '/spatial/diagnostics')).toMatchObject({id: 'spatial', hidden: true});
});

it('mounts /spatial, the engine page, as its own lazy route', async () => {
  const extra = SCREENS.find(s => s.id === 'spatial')?.extra?.find(e => e.path === '/spatial');
  expect(extra?.load).toBeTypeOf('function');
  const page = await extra!.load!();
  expect(page.default.name).toBe('Spatial');
});

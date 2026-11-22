// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { SCREENS } from '../registry';

it('mounts the diagnostics link target in the dashboard', () => {
  expect(SCREENS.find(s => s.path === '/spatial/diagnostics')).toMatchObject({id: 'spatial', hidden: true});
});

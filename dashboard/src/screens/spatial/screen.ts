// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'spatial', path: '/spatial/diagnostics', title: 'Spatial diagnostics',
  icon: 'settings', section: 'System', order: 260, hidden: true,
  hue: ['#436880', '#31435d'], load: () => import('./Diagnostics'),
  // The spatial engine (issue #814): its own lazy chunk; three.js loads after the readiness probe only.
  extra: [{ path: '/spatial', load: () => import('./Spatial') }],
};
export default screen;

// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'spatial', path: '/spatial/diagnostics', title: 'Spatial diagnostics',
  icon: 'settings', section: 'System', order: 260, hidden: true,
  hue: ['#436880', '#31435d'], load: () => import('./Diagnostics'),
};
export default screen;

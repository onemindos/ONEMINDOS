// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'control-hub',
  path: '/control-hub',
  title: 'Control Hub',
  icon: 'hub',
  section: 'System',
  order: 150,
  hue: ['#e5484d', '#7c0d16'],
  pro: true,
  load: () => import('../../pages/ControlHub').then((m) => ({ default: m.ControlHub })),
};
export default screen;

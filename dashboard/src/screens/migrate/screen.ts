// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'migrate',
  path: '/migrate',
  title: 'Move from a cluster',
  icon: 'hub',
  section: 'System',
  order: 135,
  hue: ['#8f7cf0', '#4a37b5'],
  pro: true,
  load: () => import('../../pages/Migrate').then((m) => ({ default: m.Migrate })),
};
export default screen;

// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'activity',
  path: '/activity',
  title: 'Activity',
  icon: 'activity',
  section: 'primary',
  order: 40,
  hue: ['#22c5b0', '#0b7a6c'],
  load: () => import('../../pages/Activity').then((m) => ({ default: m.Activity })),
};
export default screen;

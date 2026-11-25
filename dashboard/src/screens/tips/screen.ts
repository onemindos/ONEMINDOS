// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'tips',
  path: '/tips',
  title: 'Tips',
  icon: 'info',
  section: 'Your box',
  order: 106,
  hue: ['#22c5b0', '#0b7a6c'],
  load: () => import('../../pages/Tips').then((m) => ({ default: m.Tips })),
  extra: [{ path: '/tips/:tipId' }],
};

export default screen;

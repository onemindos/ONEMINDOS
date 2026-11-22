// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'home',
  path: '/',
  title: 'Home',
  icon: 'home',
  section: 'primary',
  order: 10,
  dock: 1,
  hue: ['#ff4d55', '#b3101c'],
  load: () => import('../../pages/Home').then((m) => ({ default: m.Home })),
};
export default screen;

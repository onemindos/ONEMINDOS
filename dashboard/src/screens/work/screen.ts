// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'work',
  path: '/work',
  title: 'Work',
  icon: 'check',
  hue: ['var(--om-color-accent)', 'var(--om-color-accent)'],
  section: 'Your box',
  order: 86,
  load: () => import('../../pages/Work').then((module) => ({ default: module.Work })),
};
export default screen;

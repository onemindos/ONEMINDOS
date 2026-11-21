// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'machines',
  path: '/machines',
  title: 'Machines',
  icon: 'monitor',
  section: 'Your box',
  order: 70,
  hue: ['#9b7bf7', '#5b2bc8'],
  load: () => import('../../pages/Machines').then((m) => ({ default: m.Machines })),
};
export default screen;

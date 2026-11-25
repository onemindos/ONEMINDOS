// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'troubleshoot',
  path: '/troubleshoot',
  title: 'Troubleshoot',
  icon: 'alert',
  section: 'Your box',
  order: 105,
  hue: ['#c2703d', '#7a3f1a'],
  pro: true,
  load: () => import('../../pages/Troubleshoot').then((m) => ({ default: m.Troubleshoot })),
};
export default screen;

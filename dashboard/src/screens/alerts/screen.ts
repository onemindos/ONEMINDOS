// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'alerts',
  path: '/alerts',
  title: 'Alerts',
  icon: 'bell',
  section: 'Your box',
  order: 80,
  hue: ['#f4637c', '#b0123a'],
  load: () => import('../../pages/Alerts').then((m) => ({ default: m.Alerts })),
};
export default screen;

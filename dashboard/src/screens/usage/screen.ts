// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'usage',
  path: '/usage',
  title: 'Live usage',
  icon: 'gauge',
  section: 'Your box',
  order: 85,
  hue: ['#8cc63f', '#3f7a0c'],
  pro: true,
  load: () => import('../../pages/Usage').then((m) => ({ default: m.Usage })),
};
export default screen;

// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'installed',
  path: '/installed',
  title: 'Installed',
  icon: 'check',
  section: 'Your box',
  order: 50,
  hue: ['#34c77b', '#147a45'],
  load: () => import('../../pages/Installed').then((m) => ({ default: m.Installed })),
  extra: [
    { path: '/installed/:appId' },
  ],
};
export default screen;

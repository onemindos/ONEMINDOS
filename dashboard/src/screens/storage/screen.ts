// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'storage',
  path: '/storage',
  title: 'Storage',
  icon: 'storage',
  section: 'Your box',
  order: 90,
  hue: ['#f6a35c', '#b8460c'],
  pro: true,
  load: () => import('../../pages/Storage').then((m) => ({ default: m.Storage })),
  redirects: [{ from: '/settings/storage', to: '/storage' }],
};
export default screen;

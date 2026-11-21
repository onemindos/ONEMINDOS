// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'updates',
  path: '/updates',
  title: 'OS updates',
  icon: 'updates',
  section: 'Your box',
  order: 120,
  hue: ['#7d8794', '#3a414b'],
  pro: true,
  load: () => import('../../pages/Updates').then((m) => ({ default: m.Updates })),
  redirects: [{ from: '/settings/updates', to: '/updates' }],
};
export default screen;

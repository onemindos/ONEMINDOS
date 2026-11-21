// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'coming',
  path: '/coming',
  title: 'Coming soon',
  icon: 'info',
  section: 'Your box',
  order: 140,
  // No "Coming soon" tile in the dock or Launchpad: the page stays reachable by path for links that name it.
  hidden: true,
  hue: ['#7d8794', '#3a414b'],
  load: () => import('../../pages/Coming').then((m) => ({ default: m.Coming })),
};
export default screen;

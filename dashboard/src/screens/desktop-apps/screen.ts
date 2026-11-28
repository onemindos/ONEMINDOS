// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'desktop-apps',
  path: '/desktop-apps',
  title: 'Desktop apps',
  icon: 'monitor',
  section: 'Your box',
  order: 108,
  hue: ['#6a8fe8', '#2b4fb0'],
  pro: true,
  load: () => import('../../pages/DesktopApps').then((m) => ({ default: m.DesktopApps })),
};
export default screen;

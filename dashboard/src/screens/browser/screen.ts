// SPDX-License-Identifier: Apache-2.0
// #692: a browser app (Firefox, Chromium) in a window, with the signed-in person's own profile.
// Opened from Market and Installed for apps the gateway marks `browser`; never offered as a tile.
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'browser',
  path: '/browser/:appId',
  title: 'Browser',
  icon: 'apps',
  section: 'Your box',
  order: 57,
  hue: ['#4f9dff', '#1f5fc4'],
  hidden: true,
  load: () => import('../../shell/BrowserWindow').then((m) => ({ default: m.BrowserWindow })),
};
export default screen;

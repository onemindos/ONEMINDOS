// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'settings',
  path: '/settings',
  title: 'Settings',
  icon: 'settings',
  section: 'Your box',
  order: 130,
  dock: 6,
  hue: ['#8f99a6', '#3e4652'],
  load: () => import('../../pages/Settings').then((m) => ({ default: m.Settings })),
  extra: [
    { path: '/settings/plugin-keys', load: () => import('../../pages/PluginKeys').then((m) => ({ default: m.PluginKeys })) },
    { path: '/settings/:section' },
    // A tab and an item inside a section (Settings > Permissions > Rules > one rule): notification links open them.
    { path: '/settings/:section/:tab' },
    { path: '/settings/:section/:tab/:item' },
  ],
};
export default screen;

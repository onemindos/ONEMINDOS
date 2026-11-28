// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'settings',
  path: '/settings',
  title: 'Settings',
  icon: 'settings',
  section: 'Your box',
  order: 130,
  hue: ['#8f99a6', '#3e4652'],
  load: () => import('../../pages/Settings').then((m) => ({ default: m.Settings })),
  extra: [
    { path: '/settings/plugin-keys', load: () => import('../../pages/PluginKeys').then((m) => ({ default: m.PluginKeys })) },
    { path: '/settings/:section' },
  ],
};
export default screen;

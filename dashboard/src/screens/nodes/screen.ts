// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'nodes',
  path: '/nodes',
  title: 'Nodes',
  icon: 'nodes',
  section: 'Your box',
  order: 60,
  hue: ['#38a8f0', '#0b5f9a'],
  pro: true,
  redirects: [{ from: '/settings/devices', to: '/nodes' }],
  load: () => import('../../pages/Nodes').then((m) => ({ default: m.Nodes })),
};
export default screen;

// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'network',
  path: '/network',
  title: 'Network',
  icon: 'network',
  section: 'Your box',
  order: 107,
  hue: ['#4aa8e0', '#1d5f99'],
  pro: true,
  load: () => import('../../pages/Network').then((m) => ({ default: m.Network })),
  redirects: [{ from: '/settings/network', to: '/network' }],
};
export default screen;

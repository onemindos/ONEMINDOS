// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'automation',
  path: '/automation',
  title: 'Automation',
  icon: 'clock',
  section: 'Your box',
  order: 110,
  hue: ['#8c7cf0', '#4a3bb8'],
  pro: true,
  redirects: [{ from: '/settings/automation', to: '/automation' }],
  load: () => import('../../pages/Automation').then((m) => ({ default: m.Automation })),
};
export default screen;

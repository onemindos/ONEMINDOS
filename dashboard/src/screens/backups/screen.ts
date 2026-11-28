// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'backups',
  path: '/backups',
  title: 'Backups',
  icon: 'backups',
  section: 'Your box',
  order: 100,
  dock: 6,
  hue: ['#3fc6db', '#0c6b80'],
  pro: true,
  load: () => import('../../pages/Backups').then((m) => ({ default: m.Backups })),
  redirects: [{ from: '/settings/backups', to: '/backups' }],
};
export default screen;

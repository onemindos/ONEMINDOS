// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'approvals',
  path: '/approvals',
  title: 'Approvals',
  icon: 'approvals',
  section: 'primary',
  order: 30,
  dock: 3,
  hue: ['#f59e0b', '#b45309'],
  badge: 'approvals',
  load: () => import('../../pages/Approvals').then((m) => ({ default: m.Approvals })),
};
export default screen;

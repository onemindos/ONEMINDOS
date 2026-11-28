// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'library',
  path: '/library',
  title: 'Offline library',
  icon: 'apps',
  section: 'Your box',
  order: 108,
  hue: ['#4fb286', '#1f6b4a'],
  pro: true,
  load: () => import('../../pages/Library').then((m) => ({ default: m.Library })),
};
export default screen;

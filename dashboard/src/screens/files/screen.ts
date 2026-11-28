// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'files',
  path: '/files',
  title: 'Files',
  icon: 'storage',
  section: 'Your box',
  order: 45,
  dock: 4,
  hue: ['#5fb4f0', '#1c63b0'],
  load: () => import('../../pages/Files').then((m) => ({ default: m.Files })),
};
export default screen;

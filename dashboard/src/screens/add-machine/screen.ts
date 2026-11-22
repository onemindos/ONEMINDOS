// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'add-machine',
  path: '/add-machine',
  title: 'Add a machine',
  icon: 'nodes',
  section: 'Your box',
  order: 65,
  hue: ['#4cc38a', '#13734c'],
  pro: true,
  load: () => import('../../pages/AddMachine').then((m) => ({ default: m.AddMachine })),
};
export default screen;

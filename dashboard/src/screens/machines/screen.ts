// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'machines',
  path: '/machines',
  title: 'Machines',
  icon: 'monitor',
  section: 'Your box',
  order: 70,
  dock: 7,
  hue: ['#9b7bf7', '#5b2bc8'],
  pro: true,
  load: () => import('../../pages/Machines').then((m) => ({ default: m.Machines })),
  extra: [{ path: '/machines/:name', load: () => import('../../pages/MachineConsole').then((m) => ({ default: m.MachineConsoleWindow })) }],
};
export default screen;

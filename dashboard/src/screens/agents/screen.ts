// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'agents',
  path: '/agents',
  title: 'AI & Agents',
  icon: 'agent',
  section: 'System',
  order: 160,
  hue: ['#d96cf0', '#8a1fa3'],
  pro: true,
  load: () => import('../../pages/Agents').then((m) => ({ default: m.Agents })),
};
export default screen;

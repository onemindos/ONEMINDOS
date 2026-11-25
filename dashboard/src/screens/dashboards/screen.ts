// SPDX-License-Identifier: Apache-2.0
import { TILE_HUES } from '@onemind/ui';
import type { ScreenDef } from '../types';

const hue = TILE_HUES.find((tile) => tile.name === 'blue')!;

const screen: ScreenDef = {
  id: 'dashboards',
  path: '/dashboards',
  title: 'Dashboards',
  icon: 'gauge',
  section: 'Your box',
  order: 86,
  hue: [hue.a, hue.b],
  pro: true,
  load: () => import('../../pages/Dashboards').then((m) => ({ default: m.Dashboards })),
};

export default screen;

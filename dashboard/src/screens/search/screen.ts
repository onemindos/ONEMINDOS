// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'search',
  path: '/search',
  title: 'Search',
  icon: 'search',
  section: 'Your box',
  order: 47,
  hue: ['#8b7fe8', '#4a3fb0'],
  load: () => import('../../pages/Search').then((m) => ({ default: m.Search })),
};
export default screen;

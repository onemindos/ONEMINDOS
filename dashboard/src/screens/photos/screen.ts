// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'photos',
  path: '/photos',
  title: 'Photos',
  icon: 'apps',
  section: 'Your box',
  order: 75,
  hue: ['#6d84ff', '#3340c4'],
  load: () => import('../../pages/Photos').then((m) => ({ default: m.Photos })),
};
export default screen;

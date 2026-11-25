// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'world', path: '/world', title: 'World', icon: 'network', section: 'Your box',
  order: 68, hue: ['var(--om-color-accent)', 'var(--om-color-info-fg)'], pro: true,
  load: () => import('../../pages/WorldSources').then((module) => ({ default: module.WorldSources })),
};
export default screen;

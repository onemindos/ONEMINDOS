// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

// Map v0 (#653): the box, its nodes, machines and assets on one plan. Second in the dock (Atlas design, "The map");
// 1.5 sits it between Home (1) and Market (2) without renumbering the other screens' files.
const screen: ScreenDef = {
  id: 'map', path: '/map', title: 'Map', icon: 'map', section: 'Your box', order: 59, dock: 1.5,
  hue: ['var(--om-color-accent)', 'var(--om-color-ok-fg)'],
  load: () => import('../../pages/map/MapScreen').then((m) => ({ default: m.MapScreen })),
};
export default screen;

// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

// Atlas Plugins (design screen 10): installed plugins, the five defined places each one shows up in, and what to do when one
// misbehaves. Owner and adults only (Pro); every change is a request that waits in Approvals (D-027).
const screen: ScreenDef = {
  id: 'plugins',
  path: '/plugins',
  title: 'Plugins',
  icon: 'apps',
  section: 'System',
  order: 170,
  hue: ['var(--om-color-accent)', 'var(--om-color-info-fg)'],
  pro: true,
  load: () => import('../../pages/Plugins').then((m) => ({ default: m.Plugins })),
};
export default screen;

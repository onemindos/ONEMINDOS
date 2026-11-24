// SPDX-License-Identifier: Apache-2.0
// FD-06: one app page (state dot, facts, Usage/Logs/Alerts/Backups/Access/Trust/Help tabs). Opens as a
// window over the desktop (D-016). The gateway already links its app notifications to /apps/<id>.
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'app',
  path: '/apps/:appId',
  title: 'App',
  icon: 'apps',
  section: 'Your box',
  order: 55,
  hue: ['#6d84ff', '#3340c4'],
  hidden: true,
  load: () => import('../../pages/AppPage').then((m) => ({ default: m.AppPage })),
};
export default screen;

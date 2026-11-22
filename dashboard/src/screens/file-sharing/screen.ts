// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'file-sharing',
  path: '/file-sharing',
  title: 'File sharing',
  icon: 'link',
  section: 'Your box',
  order: 105,
  hue: ['#5bbf6a', '#1f7a35'],
  pro: true,
  load: () => import('../../pages/FileSharing').then((m) => ({ default: m.FileSharing })),
  redirects: [{ from: '/settings/file-sharing', to: '/file-sharing' }],
};
export default screen;

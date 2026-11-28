// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

const screen: ScreenDef = {
  id: 'market',
  path: '/market',
  title: 'Market',
  icon: 'apps',
  section: 'primary',
  order: 20,
  dock: 2,
  hue: ['#6d84ff', '#3340c4'],
  load: () => import('../../pages/Market').then((m) => ({ default: m.Market })),
  extra: [
    { path: '/market/requests', load: () => import('../../pages/market/MarketRequests').then((m) => ({ default: m.MarketRequests })) },
    { path: '/market/:appId' },
    { path: '/built-in', load: () => import('../../pages/BuiltIn').then((m) => ({ default: m.BuiltInTab })) },
    { path: '/sources', load: () => import('../../pages/AppSources').then((m) => ({ default: m.Sources })), owner: 'Community sources' },
    { path: '/custom', load: () => import('../../pages/AppCustom').then((m) => ({ default: m.CustomApps })), owner: 'Custom apps' },
    { path: '/compose', load: () => import('../../pages/AppSources').then((m) => ({ default: m.ComposeImport })), owner: 'Import Compose' },
  ],
};
export default screen;

// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'default-apps', load: () => import('../../pages/default-apps/DefaultApps').then((m) => ({ default: m.DefaultApps })) };
export default page;

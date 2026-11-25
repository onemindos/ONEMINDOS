// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// #617: the built-in apps (GET /v1/system-apps), the same list as the Market's Built in tab.
const page: SettingsPageDef = { id: 'apps', load: () => import('../../pages/BuiltIn').then((m) => ({ default: m.SettingsApps })) };
export default page;

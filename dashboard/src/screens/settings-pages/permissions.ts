// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'permissions', load: () => import('../../pages/SettingsSecurity').then((module) => ({ default: module.SettingsPermissions })) };
export default page;

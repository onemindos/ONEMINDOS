// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'security', load: () => import('../../pages/SettingsSecurity').then((module) => ({ default: module.SettingsSecurity })) };
export default page;

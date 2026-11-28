// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'activity-monitor', load: () => import('../../pages/SettingsSecurity').then((module) => ({ default: module.SettingsActivityMonitor })) };
export default page;

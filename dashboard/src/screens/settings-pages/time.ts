// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'time', load: () => import('../../pages/SettingsTimeRecovery').then((module) => ({ default: module.SettingsDateTime })) };
export default page;

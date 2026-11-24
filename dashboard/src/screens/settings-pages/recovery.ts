// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'recovery', load: () => import('../../pages/SettingsTimeRecovery').then((module) => ({ default: module.SettingsRecoveryReset })) };
export default page;

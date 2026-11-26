// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'verification', load: () => import('../../pages/VerificationLevels').then((module) => ({ default: module.VerificationLevels })) };
export default page;

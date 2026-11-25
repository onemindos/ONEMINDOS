// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = {
  id: 'accessibility',
  load: () => import('../../pages/SettingsAccessibility').then((module) => ({ default: module.SettingsAccessibility })),
};
export default page;

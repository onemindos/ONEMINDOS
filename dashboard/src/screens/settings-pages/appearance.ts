// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'appearance', load: () => import('../../pages/SettingsAppearance').then((m) => ({ default: m.SettingsAppearance })) };
export default page;

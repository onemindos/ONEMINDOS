// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'region', load: () => import('../../pages/SettingsRegion').then((m) => ({ default: m.SettingsRegion })) };
export default page;

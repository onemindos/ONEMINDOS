// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'care', load: () => import('../../pages/Care').then(m => ({ default: m.Care })) };
export default page;

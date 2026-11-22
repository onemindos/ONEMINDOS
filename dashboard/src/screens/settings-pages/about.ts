// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'about', load: () => import('../../pages/SettingsAbout').then((m) => ({ default: m.SettingsAbout })) };
export default page;

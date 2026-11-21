// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'users', load: () => import('../../pages/Users').then((m) => ({ default: m.Users })) };
export default page;

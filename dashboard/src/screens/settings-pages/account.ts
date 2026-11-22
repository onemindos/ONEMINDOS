// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'account', load: () => import('../../pages/Account').then((m) => ({ default: m.Account })) };
export default page;
